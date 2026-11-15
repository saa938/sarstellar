"""Remote reads of NISAR GCOV (HDF5) and OPERA RTC-S1 (GeoTIFF) windows from ASF / Earthdata.

A GCOV file is 2-9 GB, so nothing here downloads one: `open_remote_h5` serves it to h5py through an
fsspec block cache, and `read_gcov_window` pulls just the HHHH / HVHV / mask pixels under the
analysis grid. Every network fetch goes through `with_retries`, because ASF answers with a
transient 502 now and then (a 502 once crashed a bare h5py read mid-file).
"""

from __future__ import annotations

import logging
import math
import os
import time
from collections.abc import Callable
from contextlib import ExitStack
from typing import Any

import h5py
import numpy as np

from .grid import (
    Grid,
    block_mean,
    block_valid_frac,
    grid_for_bbox,
    to_grid_with_coverage,
    valid_mask,
)

log = logging.getLogger(__name__)

H5_BLOCK_BYTES = 8 * 2**20  # fsspec blockcache block size for GCOV files
H5_PAGE_BUF_BYTES = 16 * 2**20  # h5py page buffer; NISAR files use paged aggregation
H5_CHUNK_CACHE_BYTES = 4 * 2**20  # h5py raw-data chunk cache
TIF_BLOCK_BYTES = 2 * 2**20  # blockcache size for RTC GeoTIFFs (COG tiles are small)
L30_SAMPLE_M = 30.0  # the coarser lattice that `HH30` / `HV30` simulate
RTC_MIN_VALID_FRAC = 0.5  # a Sentinel-1 block needs half its area valid, like a NISAR block

_IDENT = "/science/LSAR/identification"
_GRID_A = "/science/LSAR/GCOV/grids/frequencyA"
_SWATH_A = "/science/LSAR/GCOV/metadata/sourceData/swaths/frequencyA"


# --- login and retries --------------------------------------------------------------------------


def https_fs():
    """An fsspec HTTPS filesystem that carries an Earthdata login.

    Credentials come from `EARTHDATA_USERNAME` / `EARTHDATA_PASSWORD` when both are set (Modal),
    otherwise from `~/_netrc` (a developer machine). Never prompts.
    """
    import earthaccess  # lazy: slow to import, and offline code never needs it

    has_env = bool(os.environ.get("EARTHDATA_USERNAME") and os.environ.get("EARTHDATA_PASSWORD"))
    auth = earthaccess.login(strategy="environment" if has_env else "netrc", persist=False)
    if not auth.authenticated:
        raise RuntimeError(
            "Earthdata login failed: set EARTHDATA_USERNAME and EARTHDATA_PASSWORD, or add an "
            "urs.earthdata.nasa.gov entry to ~/_netrc"
        )
    return earthaccess.get_fsspec_https_session()


def with_retries(fn: Callable, max_retries: int = 6, retries: list[str] | None = None) -> Callable:
    """Wrap `fn` so a failing call is tried again, with exponential backoff (1, 2, 4, ... s).

    `max_retries` is the total number of tries. After the last one fails the wrapper raises
    `IOError`, chained to the final error. Each failure that is followed by another try is logged
    and, if `retries` is given, appended to it as "ExcType: message".
    """
    if max_retries < 1:
        raise ValueError("max_retries must be at least 1")

    def wrapper(*args, **kwargs):
        for attempt in range(1, max_retries + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # network failures arrive as many types: aiohttp, OSError, ...
                note = f"{type(exc).__name__}: {str(exc)[:80]}"
                if attempt == max_retries:
                    raise OSError(f"remote read failed after {max_retries} tries: {note}") from exc
                delay = 2 ** (attempt - 1)
                log.warning("remote read failed (try %d of %d), retrying in %d s: %s",
                            attempt, max_retries, delay, note)
                if retries is not None:
                    retries.append(note)
                time.sleep(delay)

    return wrapper


def _open_cached(url, fs, block_bytes: int, max_retries: int, retries: list[str] | None):
    """Open `url` for reading through an fsspec block cache whose fetches retry with backoff."""
    f = with_retries(fs.open, max_retries, retries)(
        url, "rb", cache_type="blockcache", block_size=block_bytes
    )
    f.cache.fetcher = with_retries(f.cache.fetcher, max_retries, retries)
    return f


def open_remote_h5(url, fs, max_retries: int = 6, retries: list[str] | None = None):
    """Open a remote HDF5 file lazily. Returns (file object, h5py.File); close both when done.

    `retries`, if given, collects one note per retried fetch (see `with_retries`).
    """
    f = _open_cached(url, fs, H5_BLOCK_BYTES, max_retries, retries)
    try:
        h = h5py.File(f, "r", page_buf_size=H5_PAGE_BUF_BYTES, rdcc_nbytes=H5_CHUNK_CACHE_BYTES)
    except BaseException:
        f.close()
        raise
    return f, h


# --- GCOV ---------------------------------------------------------------------------------------


def _scalar(ds) -> Any:
    """An h5py scalar dataset as a plain Python value (bytes decoded, numpy scalars unwrapped)."""
    v = ds[()]
    if isinstance(v, bytes):
        return v.decode()
    return v.item() if hasattr(v, "item") else v


def _as_bool(v) -> bool:
    return v if isinstance(v, bool) else str(v).strip().lower() in ("true", "1")


def _window_in_file(grid: Grid, x0: float, y0: float, step: float) -> tuple[int, int, int, int]:
    """Where the grid's window sits on a file's pixel lattice: (row0, col0, rows, cols).

    (x0, y0) is the centre of the file's first pixel and `step` its size in metres. Row0/col0 can
    be negative or run past the file when the window overhangs the frame.
    """
    col0 = (grid.xmin + step / 2 - x0) / step  # first pixel whose centre is inside the window
    row0 = (y0 - (grid.ymax - step / 2)) / step
    off_x, off_y = abs(col0 - round(col0)) * step, abs(row0 - round(row0)) * step  # metres
    if off_x > 1e-3 or off_y > 1e-3:
        raise ValueError(
            f"the grid is not on this granule's {step:g} m pixel lattice "
            f"(off by {off_x:.3f} m in x, {off_y:.3f} m in y)"
        )
    cols = round((grid.xmax - grid.xmin) / step)
    rows = round((grid.ymax - grid.ymin) / step)
    return round(row0), round(col0), rows, cols


def read_gcov_window(url, bbox, fs, grid: Grid | None = None):
    """Read frequency A HHHH / HVHV / mask for the grid window of a remote GCOV granule.

    With no `grid`, one is built for the lon/lat `bbox` in this file's UTM zone. Pass the grid
    from an earlier date to read exactly the same ground pixels (and to get `ValueError("EPSG
    differs")` if this file is in another zone: a stack never mixes zones in one series).

    Returns (meta, {"HH", "HV", "mask"}, grid). The arrays are at the file's native posting, linear
    power (float32) and the raw uint8 mask, shape (ny * block, nx * block) with block = 10 at 10 m.
    Where the window overhangs the granule's frame, HH/HV are NaN and mask is 255 (fill).
    """
    retries: list[str] = []
    t0 = time.perf_counter()
    f, h = open_remote_h5(url, fs, retries=retries)
    t_open = time.perf_counter() - t0
    try:
        ident, g, sw = h[_IDENT], h[_GRID_A], h[_SWATH_A]
        epsg = int(_scalar(g["projection"]))
        if grid is None:
            grid = grid_for_bbox(bbox, epsg)
        elif grid.epsg != epsg:
            raise ValueError(f"EPSG differs: grid is {grid.epsg}, granule is {epsg}")
        dx, dy = float(_scalar(g["xCoordinateSpacing"])), float(_scalar(g["yCoordinateSpacing"]))
        if dx <= 0 or abs(dy + dx) > 1e-6:
            raise ValueError(f"expected a north-up grid with square pixels, got dx={dx}, dy={dy}")
        if abs(round(grid.res / dx) * dx - grid.res) > 1e-6:
            raise ValueError(f"{dx:g} m pixels do not tile the {grid.res:g} m block grid")
        x, y = g["xCoordinates"][:], g["yCoordinates"][:]
        x_span, y_span = (len(x) - 1) * dx, (len(y) - 1) * dx
        if abs(x[-1] - x[0] - x_span) > 1e-3 or abs(y[0] - y[-1] - y_span) > 1e-3:
            raise ValueError("the granule's coordinates are not evenly spaced")
        file_ny, file_nx = g["HHHH"].shape

        row0, col0, rows, cols = _window_in_file(grid, float(x[0]), float(y[0]), dx)
        r_lo, r_hi = max(row0, 0), min(row0 + rows, file_ny)
        c_lo, c_hi = max(col0, 0), min(col0 + cols, file_nx)
        if r_lo >= r_hi or c_lo >= c_hi:
            raise ValueError("the grid window does not overlap this granule's frame")

        t0 = time.perf_counter()
        hh = np.full((rows, cols), np.nan, dtype="float32")
        hv = np.full((rows, cols), np.nan, dtype="float32")
        mask = np.full((rows, cols), 255, dtype="uint8")
        src = np.s_[r_lo:r_hi, c_lo:c_hi]
        dst = np.s_[r_lo - row0 : r_hi - row0, c_lo - col0 : c_hi - col0]
        for name, out in (("HHHH", hh), ("HVHV", hv), ("mask", mask)):
            out[dst] = g[name][src]
        t_read = time.perf_counter() - t0

        meta = {
            "granule": _scalar(ident["granuleId"]),
            "date": _scalar(ident["zeroDopplerStartTime"])[:19],
            "track": _scalar(ident["trackNumber"]),
            "frame": _scalar(ident["frameNumber"]),
            "direction": _scalar(ident["orbitPassDirection"]),
            "crid": _scalar(ident["compositeReleaseId"]),
            "productVersion": _scalar(ident["productVersion"]),
            "isMixedMode": _as_bool(_scalar(ident["isMixedMode"])),
            "isFullFrame": _as_bool(_scalar(ident["isFullFrame"])),
            "acquiredRangeBandwidth_freqA_Hz": float(_scalar(sw["acquiredRangeBandwidth"])),
            "processedRangeBandwidth_freqA_Hz": float(_scalar(sw["processedRangeBandwidth"])),
            "polarizations": [
                p.decode() if isinstance(p, bytes) else str(p) for p in g["listOfPolarizations"][:]
            ],
            "epsg": epsg,
            "posting_m": dx,
            "window_shape": [rows, cols],
            "t_open_s": round(t_open, 2),
            "t_read_s": round(t_read, 2),
            "http_retries": retries,
        }
    finally:
        h.close()
        f.close()
    return meta, {"HH": hh, "HV": hv, "mask": mask}, grid


def read_gcov_blocks(url, bbox, fs, grid: Grid | None = None):
    """Read a GCOV window and average it to 1-ha blocks, in linear power.

    Returns (meta, {"HH", "HV", "HH30", "HV30", "valid_frac"}, grid), each array shaped
    `grid.shape`. A pixel is valid when mask is 1..254 and HH and HV are both finite and > 0.
    `HH` / `HV` are NaN where under half the block is valid. `HH30` / `HV30` average only the
    pixels on a 30 m lattice (row and column both multiples of 3 at 10 m posting), which
    simulates a 30 m sensor; their 50% rule counts those sampled pixels only. `valid_frac` is the
    share of each block's pixels that are valid.
    """
    meta, arrays, grid = read_gcov_window(url, bbox, fs, grid)
    hh, hv = arrays["HH"], arrays["HV"]
    ny, nx = grid.shape
    block = hh.shape[0] // ny
    if block < 1 or hh.shape != (ny * block, nx * block):
        raise ValueError(f"window {hh.shape} is not a whole number of blocks of grid {grid.shape}")
    valid = valid_mask(arrays["mask"], hh, hv)
    stride = max(1, round(L30_SAMPLE_M / (grid.res / block)))
    sample = np.zeros(hh.shape, dtype=bool)
    sample[::stride, ::stride] = True
    blocks = {
        "HH": block_mean(hh, valid, block),
        "HV": block_mean(hv, valid, block),
        "HH30": block_mean(hh, valid, block, sample=sample),
        "HV30": block_mean(hv, valid, block, sample=sample),
        "valid_frac": block_valid_frac(valid, block),
    }
    return meta, blocks, grid


# --- RTC-S1 -------------------------------------------------------------------------------------


def _rtc_window(ds, grid: Grid):
    """The pixel window of raster `ds` that covers the grid (plus a pixel of margin), or None."""
    from rasterio.crs import CRS
    from rasterio.warp import transform_bounds
    from rasterio.windows import Window, from_bounds

    left, bottom, right, top = transform_bounds(
        CRS.from_epsg(grid.epsg), ds.crs, grid.xmin, grid.ymin, grid.xmax, grid.ymax, densify_pts=21
    )
    w = from_bounds(left, bottom, right, top, transform=ds.transform)
    col0, row0 = max(math.floor(w.col_off) - 1, 0), max(math.floor(w.row_off) - 1, 0)
    col1 = min(math.ceil(w.col_off + w.width) + 1, ds.width)
    row1 = min(math.ceil(w.row_off + w.height) + 1, ds.height)
    if col1 <= col0 or row1 <= row0:
        return None
    return Window(col0, row0, col1 - col0, row1 - row0)


def _open_tif(url, fs, max_retries: int, stack: ExitStack):
    import rasterio

    f = _open_cached(url, fs, TIF_BLOCK_BYTES, max_retries, None)
    stack.callback(f.close)  # registered first, so it runs after the dataset closes
    return stack.enter_context(rasterio.open(f))


def read_rtc_to_grid(
    urls: list[str], grid: Grid, fs, max_retries: int = 6
) -> dict[str, np.ndarray]:
    """Mosaic OPERA RTC-S1 burst GeoTIFFs onto the block grid. Returns {"VV", "VH"}, linear power.

    `urls` are burst polarization files ending `_VV.tif` or `_VH.tif`; pass the VV and VH URLs
    together. Each burst's `_mask.tif` sits beside its data and is fetched once per burst. Pixels
    with a non-zero mask (shadow, layover, fill), NaN, or a value <= 0 are dropped.

    A block follows the NISAR rule: a burst only contributes to a block where at least
    `RTC_MIN_VALID_FRAC` (50%) of the block's area holds valid pixels of that burst. Area outside
    the burst's raster counts as not valid. Overlapping bursts are then mosaicked weighted by
    their valid area in the block, which is the same as pooling their valid pixels. A block no
    burst covers well enough, and a polarization with no URLs, come back NaN. (A seam block that
    each of two bursts covers under half, but that they cover together, is NaN.)
    """
    bursts: dict[str, dict[str, str]] = {}
    for url in urls:
        prefix, _, tail = url.rpartition("_")
        pol = tail.removesuffix(".tif")
        if pol not in ("VV", "VH"):
            raise ValueError(f"expected an RTC burst URL ending _VV.tif or _VH.tif, got {url!r}")
        bursts.setdefault(prefix, {})[pol] = url

    total = {pol: np.zeros(grid.shape) for pol in ("VV", "VH")}
    weight = {pol: np.zeros(grid.shape) for pol in ("VV", "VH")}
    for prefix, pol_urls in bursts.items():
        with ExitStack() as stack:
            mask_ds = None
            for pol, url in pol_urls.items():
                ds = _open_tif(url, fs, max_retries, stack)
                win = _rtc_window(ds, grid)
                if win is None:  # this burst does not reach the grid: skip it, mask included
                    continue
                if mask_ds is None:
                    mask_ds = _open_tif(prefix + "_mask.tif", fs, max_retries, stack)
                if mask_ds.shape != ds.shape or mask_ds.transform != ds.transform:
                    raise ValueError(f"{prefix}_mask.tif is not on the same raster as {url}")
                v = ds.read(1, window=win).astype("float64")
                v[(mask_ds.read(1, window=win) != 0) | ~np.isfinite(v) | (v <= 0)] = np.nan
                mean, frac = to_grid_with_coverage(
                    v, ds.window_transform(win), ds.crs, grid, RTC_MIN_VALID_FRAC
                )
                ok = np.isfinite(mean)  # the block has at least half valid pixels from this burst
                total[pol][ok] += frac[ok] * mean[ok]  # valid-area-weighted sum of block means
                weight[pol][ok] += frac[ok]
    return {
        pol: np.where(weight[pol] > 0, total[pol] / np.maximum(weight[pol], 1e-12), np.nan)
        for pol in total
    }

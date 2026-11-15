"""SARstellar v2: a stage's full NISAR series, as 1-ha blocks (the dance) and as map imagery.

The change engine (`features.py`) compares two dates on clean full frames. A stage needs every
pass, so this module relaxes three rules, each recorded in the output metadata:

* Partial frames are allowed. Greenland's 77 MHz ice mode and the Tonle Sap passes only arrive
  as partial frames. Frames of one date are composited; gaps stay NaN.
* HH-only passes (single-pol "SH" ice mode) are read without HV.
* Any posting that tiles the 100 m block (5, 10, 20 m) is accepted, so 20 MHz stacks
  (Amazon, Okavango) work as well as 40 MHz ones.

A series still never mixes track, direction, bandwidth, polarization mode or processing CRID.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

import numpy as np

from . import read as _read
from .grid import BLOCK_M, block_mean, block_valid_frac, valid_mask
from .search import _GCOV_UR_TAIL, dedupe, search_gcov
from .types import Grid, Granule

log = logging.getLogger(__name__)

# Diagonal covariance terms we read when present (VH duplicates HV by reciprocity).
POL_DATASETS = {"HH": "HHHH", "HV": "HVHV", "VV": "VVVV"}
IMG_DB_MIN, IMG_DB_MAX = -40.0, 10.0  # image quantization range; byte 0 = no data


@dataclass
class StageStack:
    """Same-mode passes over a stage: one track, direction, bandwidth, pol mode and CRID."""

    track: int
    direction: str
    bandwidth_mhz: float
    mode: str  # frequency-A polarization mode: DH, QP, SH, DV, ...
    crid: str
    granules: list[Granule]

    @property
    def dates(self) -> list[date]:
        return sorted({g.start.date() for g in self.granules})

    @property
    def has_hh_hv(self) -> bool:
        return self.mode in ("DH", "QP")

    def granules_by_date(self) -> dict[date, list[Granule]]:
        out: dict[date, list[Granule]] = defaultdict(list)
        for g in self.granules:
            out[g.start.date()].append(g)
        return dict(sorted(out.items()))

    def summary(self) -> dict:
        return {
            "track": self.track, "direction": self.direction,
            "bandwidth_mhz": self.bandwidth_mhz, "mode": self.mode, "crid": self.crid,
            "n_granules": len(self.granules), "n_dates": len(self.dates),
            "first": str(self.dates[0]), "last": str(self.dates[-1]),
            "partial_or_mixed": sum(g.mixed_mode for g in self.granules),
        }


def _mode(g: Granule) -> str:
    tail = _GCOV_UR_TAIL.search(g.ur)
    return tail["pol"][:2] if tail else ""


def stage_stacks(bbox, start: date, end: date) -> list[StageStack]:
    """All same-mode stacks over `bbox`, partial frames included, best first.

    Best = has both HH and HV, then most dates, then the wider bandwidth, then most recent.
    Passes narrower than 20 MHz (the 5 MHz frequency B) never join.
    """
    groups: dict[tuple, list[Granule]] = defaultdict(list)
    for g in dedupe(search_gcov(bbox, start, end)):
        if g.bandwidth_mhz < 20.0:
            continue
        mode = _mode(g)
        if not mode:
            continue
        groups[(g.track, g.direction, g.bandwidth_mhz, mode, g.crid)].append(g)
    stacks = [
        StageStack(t, d, b, m, c, sorted(v, key=lambda g: (g.start, g.frame)))
        for (t, d, b, m, c), v in groups.items()
    ]
    stacks.sort(key=lambda s: (not s.has_hh_hv, -len(s.dates), -s.bandwidth_mhz,
                               -s.dates[-1].toordinal(), s.track, s.direction, s.crid))
    return stacks


def probe_epsg(url: str, fs=None) -> int:
    """The UTM EPSG code of a granule's frequency-A grid."""
    fs = fs or _read.https_fs()
    f, h = _read.open_remote_h5(url, fs)
    try:
        return int(_read._scalar(h[_read._GRID_A]["projection"]))
    finally:
        h.close()
        f.close()


def _to_img_bytes(db: np.ndarray) -> np.ndarray:
    """dB -> uint8 with 0 = no data, 1..255 spanning IMG_DB_MIN..IMG_DB_MAX."""
    scaled = (np.clip(db, IMG_DB_MIN, IMG_DB_MAX) - IMG_DB_MIN) / (IMG_DB_MAX - IMG_DB_MIN)
    out = np.where(np.isfinite(db), 1 + np.round(scaled * 254), 0)
    return out.astype("uint8")


def read_stage_granule(url: str, grid: Grid, img_res: float = 20.0, fs=None):
    """Read one granule over a stage grid.

    Returns None when the granule is in another UTM zone, misses the grid, or has a posting
    that does not tile 100 m. Otherwise `(meta, blocks, image)`:
      blocks: {"HH", "HV"?, "VV"?: float32 dB [ny, nx] (NaN = under half valid), "valid_frac"}
      image:  {"HH", "HV"?, "VV"?: uint8 [ny_i, nx_i] quantized dB, 0 = no data}
    """
    fs = fs or _read.https_fs()
    retries: list[str] = []
    t0 = time.perf_counter()
    f, h = _read.open_remote_h5(url, fs, retries=retries)
    try:
        ident, g = h[_read._IDENT], h[_read._GRID_A]
        epsg = int(_read._scalar(g["projection"]))
        if epsg != grid.epsg:
            return None
        dx = float(_read._scalar(g["xCoordinateSpacing"]))
        block = round(BLOCK_M / dx)
        if block < 1 or abs(block * dx - BLOCK_M) > 1e-6:
            return None
        x, y = g["xCoordinates"][:], g["yCoordinates"][:]
        try:
            row0, col0, rows, cols = _read._window_in_file(grid, float(x[0]), float(y[0]), dx)
        except ValueError:
            return None
        file_ny, file_nx = g["HHHH"].shape
        r_lo, r_hi = max(row0, 0), min(row0 + rows, file_ny)
        c_lo, c_hi = max(col0, 0), min(col0 + cols, file_nx)
        if r_lo >= r_hi or c_lo >= c_hi:
            return None
        # Image looks: about `img_res`, and never more than ~2000 px on the long side.
        look = max(1, round(img_res / dx), -(-max(rows, cols) // 2000))
        src = np.s_[r_lo:r_hi, c_lo:c_hi]
        dst = np.s_[r_lo - row0: r_hi - row0, c_lo - col0: c_hi - col0]
        t1 = time.perf_counter()
        arrays: dict[str, np.ndarray] = {}
        for pol, name in POL_DATASETS.items():
            if name in g:
                a = np.full((rows, cols), np.nan, dtype="float32")
                a[dst] = g[name][src]
                arrays[pol] = a
        mask = np.full((rows, cols), 255, dtype="uint8")
        mask[dst] = g["mask"][src]
        t_read = time.perf_counter() - t1
        meta = {
            "granule": _read._scalar(ident["granuleId"]),
            "date": str(_read._scalar(ident["zeroDopplerStartTime"]))[:19],
            "track": int(_read._scalar(ident["trackNumber"])),
            "frame": int(_read._scalar(ident["frameNumber"])),
            "direction": _read._scalar(ident["orbitPassDirection"]),
            "crid": _read._scalar(ident["compositeReleaseId"]),
            "isFullFrame": _read._as_bool(_read._scalar(ident["isFullFrame"])),
            "isMixedMode": _read._as_bool(_read._scalar(ident["isMixedMode"])),
            "posting_m": dx,
            "pols": sorted(arrays),
            "t_open_read_s": round(time.perf_counter() - t0, 2),
            "t_read_s": round(t_read, 2),
            "http_retries": len(retries),
        }
    finally:
        h.close()
        f.close()

    valid = valid_mask(mask, *[arrays[p] for p in ("HH", "HV") if p in arrays])
    blocks: dict[str, np.ndarray] = {}
    image: dict[str, np.ndarray] = {}
    for pol, a in arrays.items():
        lin = block_mean(a, valid, block)
        with np.errstate(divide="ignore", invalid="ignore"):
            blocks[pol] = (10 * np.log10(lin)).astype("float32")
            img = block_mean(a, valid, look) if look > 1 else np.where(valid, a, np.nan)
            image[pol] = _to_img_bytes(10 * np.log10(img))
    blocks["valid_frac"] = block_valid_frac(valid, block).astype("float32")
    meta["img_res_m"] = dx * look
    return meta, blocks, image


def composite(results: list, grid: Grid) -> dict:
    """Merge per-granule results of one date: the first finite value wins per block/pixel."""
    blocks: dict[str, np.ndarray] = {}
    image: dict[str, np.ndarray] = {}
    metas = []
    for meta, b, im in results:
        metas.append(meta)
        for k, v in b.items():
            if k not in blocks:
                blocks[k] = v.copy()
            elif k == "valid_frac":
                blocks[k] = np.maximum(blocks[k], v)
            else:
                blocks[k] = np.where(np.isfinite(blocks[k]), blocks[k], v)
        for k, v in im.items():
            if k not in image:
                image[k] = v.copy()
            elif image[k].shape == v.shape:
                image[k] = np.where(image[k] > 0, image[k], v)
    return {"metas": metas, "blocks": blocks, "image": image}

"""Reference layers that sit beside the radar data.

`nlcd(grid)` returns the land-cover group of every 1-ha block. It is the stratum the detector
estimates its equivalent number of looks (ENL) for (Ruling R13): forest, grass and crops do not
share one noise level, so one scene-wide ENL over-alarms in the noisy cover.
"""

from __future__ import annotations

import logging

import numpy as np
import requests
from pyproj import Transformer

from . import read
from .grid import to_grid
from .types import Grid

log = logging.getLogger(__name__)

NLCD_WCS = "https://www.mrlc.gov/geoserver/mrlc_download/wcs"
NLCD_COVERAGE = "mrlc_download:NLCD_2021_Land_Cover_L48"  # lower 48; AK / HI / PR come back ""
NLCD_EPSG = 5070  # the file's own CRS (CONUS Albers), so the server resamples nothing
NLCD_RES_M = 30.0
NLCD_ORIGIN = (-2493045.0, 3310005.0)  # upper-left corner of the national 30 m lattice
NLCD_TIMEOUT_S = 60
NLCD_TRIES = 4

# NLCD 2021 class codes -> the seven groups the detector and the rules use.
_GROUP_CODES = {
    "forest": (41, 42, 43),
    "shrub_grass": (51, 52, 71, 72, 73, 74),
    "crops": (81, 82),  # pasture/hay and cultivated crops
    "wetland": (90, 95),  # woody and emergent herbaceous
    "developed": (21, 22, 23, 24),
    "water": (11,),
    "barren": (31, 12),  # bare rock/sand, and perennial ice/snow
}
NLCD_GROUPS_ALL = tuple(_GROUP_CODES)
_CODE_TO_GROUP = {c: g for g, codes in _GROUP_CODES.items() for c in codes}


def nlcd_group(code: int) -> str:
    """Group name for an NLCD class code; "" for nodata (0) and codes we do not use."""
    return _CODE_TO_GROUP.get(int(code), "")


def _nlcd_window(grid: Grid) -> tuple[tuple[float, float, float, float], int, int]:
    """(bbox, width, height): the grid's footprint in NLCD's own CRS, snapped to its 30 m lattice."""
    t = np.linspace(0.0, 1.0, 33)
    x = grid.xmin + (grid.xmax - grid.xmin) * t
    y = grid.ymin + (grid.ymax - grid.ymin) * t
    one = np.ones_like(t)
    xs = np.concatenate([x, x, grid.xmin * one, grid.xmax * one])
    ys = np.concatenate([grid.ymin * one, grid.ymax * one, y, y])
    px, py = Transformer.from_crs(grid.epsg, NLCD_EPSG, always_xy=True).transform(xs, ys)
    ox, oy = NLCD_ORIGIN
    pad = NLCD_RES_M  # one pixel of margin so edge blocks see their neighbours
    x0 = ox + np.floor((np.min(px) - pad - ox) / NLCD_RES_M) * NLCD_RES_M
    x1 = ox + np.ceil((np.max(px) + pad - ox) / NLCD_RES_M) * NLCD_RES_M
    y0 = oy - np.ceil((oy - (np.min(py) - pad)) / NLCD_RES_M) * NLCD_RES_M
    y1 = oy - np.floor((oy - (np.max(py) + pad)) / NLCD_RES_M) * NLCD_RES_M
    width, height = round((x1 - x0) / NLCD_RES_M), round((y1 - y0) / NLCD_RES_M)
    return (float(x0), float(y0), float(x1), float(y1)), width, height


def _fetch_nlcd(bbox, width: int, height: int) -> tuple[np.ndarray, object]:
    """One WCS GetCoverage call (retried with backoff). Returns (codes, affine transform)."""
    import rasterio

    params = {
        "service": "WCS", "version": "1.0.0", "request": "GetCoverage",
        "coverage": NLCD_COVERAGE, "crs": f"EPSG:{NLCD_EPSG}",
        "bbox": ",".join(f"{v:.1f}" for v in bbox), "width": str(width), "height": str(height),
        "format": "GeoTIFF",
    }

    def get() -> bytes:
        r = requests.get(NLCD_WCS, params=params, timeout=NLCD_TIMEOUT_S)
        r.raise_for_status()
        if r.content[:2] not in (b"II", b"MM"):  # a GeoServer error comes back as XML, status 200
            raise ValueError(f"NLCD server did not return a GeoTIFF: {r.content[:120]!r}")
        return r.content

    content = read.with_retries(get, NLCD_TRIES)()
    with rasterio.MemoryFile(content) as mem, mem.open() as ds:
        return ds.read(1), ds.transform


def nlcd(grid: Grid) -> np.ndarray:
    """NLCD land-cover group of each block of `grid`, as a [ny, nx] array of str.

    Values: forest, shrub_grass, crops, wetland, developed, water, barren. The group with the
    largest area share in the block wins (average-resample each group's 1/0 indicator onto the
    grid, then argmax). Blocks with no NLCD data are "". Any fetch error also gives all "",
    never an exception: land cover only picks the ENL stratum, and the detector falls back to
    its scene-wide ENL for unknown blocks.
    """
    unknown = np.full(grid.shape, "", dtype="<U11")
    try:
        bbox, width, height = _nlcd_window(grid)
        codes, transform = _fetch_nlcd(bbox, width, height)
    except Exception as exc:  # noqa: BLE001 - network, GeoServer, outside the lower 48: optional
        log.warning("NLCD unavailable, using scene-wide ENL: %s: %s", type(exc).__name__, exc)
        return unknown
    known = np.isin(codes, list(_CODE_TO_GROUP))
    share = np.stack([
        to_grid(np.where(known, np.isin(codes, g_codes), np.nan), transform, NLCD_EPSG, grid)
        for g_codes in _GROUP_CODES.values()
    ])  # [group, ny, nx]; NaN where the block has no known pixel
    covered = np.isfinite(share).any(axis=0)
    best = np.argmax(np.where(np.isfinite(share), share, -1.0), axis=0)
    out = np.array(NLCD_GROUPS_ALL, dtype="<U11")[best]
    return np.where(covered, out, "")

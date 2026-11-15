"""The 1-hectare block grid: snapping a lon/lat box to it, validity rules, block averaging.

Everything downstream works on one north-up grid per job: 100 m cells (10 x 10 NISAR pixels at
10 m = 1 ha) in the UTM zone of the chosen NISAR stack. Sentinel-1 is reprojected onto that same
grid with `to_grid`, so two EPSG codes never meet in one time series.
"""

from __future__ import annotations

import numpy as np
from pyproj import Transformer

from .types import Grid

BLOCK_M = 100.0  # grid cell size in metres: 1 ha
_EDGE_SAMPLES = 33  # points per box edge when projecting it (UTM bends the box's edges)


def grid_for_bbox(bbox, epsg: int) -> Grid:
    """Smallest 100 m-aligned grid in `epsg` that covers the lon/lat box [west, south, east, north].

    The box is projected edge by edge, not just at its corners, because meridians and parallels
    are curves in UTM (a box far from the zone's central meridian bows out of its corner bounds).
    """
    west, south, east, north = (float(v) for v in bbox)
    if not (west < east and south < north):
        raise ValueError(f"bbox must have west < east and south < north, got {list(bbox)}")
    t = np.linspace(0.0, 1.0, _EDGE_SAMPLES)
    along_lon, along_lat = west + (east - west) * t, south + (north - south) * t
    const = np.ones_like(t)  # times a coordinate: a constant edge value
    # points on the south edge, north edge, west edge, east edge
    lons = np.concatenate([along_lon, along_lon, west * const, east * const])
    lats = np.concatenate([south * const, north * const, along_lat, along_lat])
    xs, ys = Transformer.from_crs(4326, epsg, always_xy=True).transform(lons, lats)
    return Grid(
        epsg=int(epsg),
        xmin=float(np.floor(np.min(xs) / BLOCK_M) * BLOCK_M),
        xmax=float(np.ceil(np.max(xs) / BLOCK_M) * BLOCK_M),
        ymin=float(np.floor(np.min(ys) / BLOCK_M) * BLOCK_M),
        ymax=float(np.ceil(np.max(ys) / BLOCK_M) * BLOCK_M),
        res=BLOCK_M,
    )


def lonlat_corners(grid: Grid) -> list[list[float]]:
    """Grid corners as [lon, lat] pairs in the order the overlay bounds use: UL, UR, LR, LL."""
    to_lonlat = Transformer.from_crs(grid.epsg, 4326, always_xy=True)
    corners = [
        (grid.xmin, grid.ymax),  # upper left
        (grid.xmax, grid.ymax),  # upper right
        (grid.xmax, grid.ymin),  # lower right
        (grid.xmin, grid.ymin),  # lower left
    ]
    return [[round(c, 6) for c in to_lonlat.transform(x, y)] for x, y in corners]


def valid_mask(mask, *arrs) -> np.ndarray:
    """True where a NISAR pixel is usable: `mask` in 1..254 and every array finite and > 0."""
    mask = np.asarray(mask)
    ok = (mask >= 1) & (mask <= 254)
    for arr in arrs:
        arr = np.asarray(arr)
        ok &= np.isfinite(arr) & (arr > 0)
    return ok


def _block_sum(x: np.ndarray, block: int) -> np.ndarray:
    """Sum `x` over non-overlapping block x block tiles; a ragged last row/column is dropped."""
    ny, nx = (x.shape[0] // block) * block, (x.shape[1] // block) * block
    tiles = x[:ny, :nx].reshape(ny // block, block, nx // block, block)
    return tiles.sum(axis=(1, 3))


def block_mean(a, valid, block: int = 10, min_valid_frac: float = 0.5, sample=None) -> np.ndarray:
    """Mean of `a` over each block x block tile, using only `valid` pixels (linear, float64).

    A tile with too few valid pixels is NaN: it needs at least `min_valid_frac` of its pixels.
    With `sample` (a bool array like `a`), only sampled pixels count, and the fraction is taken
    over the tile's sampled pixels rather than all of them. That is how a coarser sampling
    lattice (one pixel in three) is simulated without every tile failing the 50% rule.
    """
    a, valid = np.asarray(a), np.asarray(valid, dtype=bool)
    if a.shape != valid.shape:
        raise ValueError(f"a and valid must have the same shape, got {a.shape} and {valid.shape}")
    if block < 1:
        raise ValueError("block must be at least 1")
    counted = valid if sample is None else valid & np.asarray(sample, dtype=bool)
    total = _block_sum(np.ones(a.shape) if sample is None else np.asarray(sample, float), block)
    n = _block_sum(counted.astype("float64"), block)
    s = _block_sum(np.where(counted, a, 0.0).astype("float64"), block)
    enough = (n > 0) & (n >= min_valid_frac * total - 1e-9)
    return np.where(enough, s / np.maximum(n, 1.0), np.nan)


def block_valid_frac(valid, block: int = 10) -> np.ndarray:
    """Fraction of each block x block tile that is valid, 0..1."""
    valid = np.asarray(valid, dtype=bool)
    return _block_sum(valid.astype("float64"), block) / float(block * block)


def to_grid(src, transform, crs, grid: Grid) -> np.ndarray:
    """Average-resample a raster (NaN = no data) onto `grid`, reprojecting if the CRS differs.

    `transform` is the source's affine transform and `crs` anything rasterio accepts for it (an
    EPSG int, "EPSG:32611", a CRS object). Cells the source does not cover come back NaN.
    """
    from rasterio.crs import CRS  # lazy: rasterio is slow to import and not needed by block_mean
    from rasterio.warp import Resampling, reproject

    out = np.full(grid.shape, np.nan, dtype="float64")
    reproject(
        np.asarray(src, dtype="float64"),
        out,
        src_transform=transform,
        src_crs=CRS.from_user_input(crs),
        src_nodata=np.nan,
        dst_transform=grid.transform(),
        dst_crs=CRS.from_epsg(grid.epsg),
        dst_nodata=np.nan,
        resampling=Resampling.average,
    )
    return out


def to_grid_with_coverage(
    src, transform, crs, grid: Grid, min_valid_frac: float = 0.5
) -> tuple[np.ndarray, np.ndarray]:
    """`to_grid` plus the 50% rule: returns (mean, valid_frac), both shaped `grid.shape`.

    `mean` averages the finite source pixels in each block and is NaN where fewer than
    `min_valid_frac` of the block's area is covered by finite pixels. `valid_frac` is that covered
    share, 0..1 (0 where the source does not reach). Area outside the source raster counts as not
    valid, so a block on a burst edge or seam is judged on the whole block, not on the sliver the
    raster happens to cover. This is the same rule `block_mean` applies to NISAR pixels.
    """
    from rasterio.transform import Affine  # lazy, like the other rasterio imports here

    src = np.asarray(src, dtype="float64")
    mean = to_grid(src, transform, crs, grid)
    # Reproject a 1/0 "usable" indicator on a canvas padded with 0 so that a block which only
    # partly overlaps the source still sees the missing part. The pad is wider than a block
    # (diagonally, once a rotated CRS is involved), so every block that touches the raster is
    # fully inside the canvas.
    pixel = min(abs(transform.a), abs(transform.e))
    pad = int(np.ceil(2 * grid.res / pixel)) + 2
    canvas = np.pad(np.isfinite(src).astype("float64"), pad)
    t = transform
    x0 = t.c - pad * (t.a + t.b)  # origin of the padded canvas: `pad` pixels up and to the left
    y0 = t.f - pad * (t.d + t.e)
    padded = Affine(t.a, t.b, x0, t.d, t.e, y0)
    frac = to_grid(canvas, padded, crs, grid)
    frac = np.clip(np.nan_to_num(frac, nan=0.0), 0.0, 1.0)
    enough = frac >= min_valid_frac - 1e-9
    return np.where(enough & np.isfinite(mean), mean, np.nan), frac

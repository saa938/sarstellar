"""Map overlays: block-grid arrays become transparent PNGs in Web Mercator (EPSG:3857).

The web map drapes each PNG over `bounds` (UL, UR, LR, LL as [lon, lat]), so the image is
reprojected from the grid's UTM zone to Web Mercator, where north is up and the box is axis-aligned.
Reprojection uses nearest-neighbour sampling: block values and agreement codes are never blended.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

from .types import Grid

# Agreement codes in the "agreement" array: NISAR only, both, Sentinel-1 only.
AGREE_L, AGREE_BOTH, AGREE_C = 1, 2, 3

MAX_SIDE_PX = 2048  # longest side of the PNG
BLOCK_PX = 8  # target pixels per 1-ha block, so blocks stay crisp when zoomed in

_AGREE_RGB = {
    AGREE_L: (0xF5, 0x9E, 0x0B),  # only NISAR
    AGREE_BOTH: (0xA7, 0x8B, 0xFA),  # both
    AGREE_C: (0x22, 0xD3, 0xEE),  # only Sentinel-1
}
_AGREE_ALPHA = 210
_DROP_RGB = (220, 38, 38)  # backscatter fell: red
_RISE_RGB = (37, 99, 235)  # backscatter rose: blue
_DELTA_FULL_DB = 6.0  # |change| at which the overlay is most opaque
_DELTA_ALPHA = (40, 235)  # opacity at ~0 dB and at the full-scale change
_DEFAULT_PERCENTILES = (2.0, 98.0)  # backscatter stretch when none is supplied

KINDS = ("delta", "agreement", "backscatter")


def _warp_to_mercator(values: np.ndarray, grid: Grid):
    """Nearest-neighbour reproject `values` to EPSG:3857; returns (array, [west, south, east, north])."""
    from rasterio.crs import CRS
    from rasterio.transform import from_bounds
    from rasterio.warp import Resampling, reproject, transform_bounds

    src_crs, dst_crs = CRS.from_epsg(grid.epsg), CRS.from_epsg(3857)
    # densify the edges: a UTM rectangle is slightly rotated and curved in Mercator
    left, bottom, right, top = transform_bounds(
        src_crs, dst_crs, grid.xmin, grid.ymin, grid.xmax, grid.ymax, densify_pts=33
    )
    ny, nx = values.shape
    longest = min(MAX_SIDE_PX, BLOCK_PX * max(ny, nx))
    width_m, height_m = right - left, top - bottom
    if width_m >= height_m:
        width, height = longest, max(1, round(longest * height_m / width_m))
    else:
        width, height = max(1, round(longest * width_m / height_m)), longest
    out = np.full((height, width), np.nan, dtype="float64")
    reproject(
        np.ascontiguousarray(values, dtype="float64"),
        out,
        src_transform=grid.transform(),
        src_crs=src_crs,
        src_nodata=np.nan,
        dst_transform=from_bounds(left, bottom, right, top, width, height),
        dst_crs=dst_crs,
        dst_nodata=np.nan,
        resampling=Resampling.nearest,
    )
    return out, (left, bottom, right, top)


def _mercator_bounds_lonlat(extent) -> list[list[float]]:
    """The Mercator extent as [lon, lat] corners in the order UL, UR, LR, LL."""
    from pyproj import Transformer

    left, bottom, right, top = extent
    to_lonlat = Transformer.from_crs(3857, 4326, always_xy=True)
    corners = [(left, top), (right, top), (right, bottom), (left, bottom)]
    return [[round(c, 6) for c in to_lonlat.transform(x, y)] for x, y in corners]


def _paint_agreement(img: np.ndarray, rgba: np.ndarray) -> None:
    for code, rgb in _AGREE_RGB.items():
        hit = img == code
        rgba[hit] = (*rgb, _AGREE_ALPHA)


def _paint_delta(img: np.ndarray, rgba: np.ndarray) -> None:
    finite = np.isfinite(img)
    safe = np.where(finite, img, 0.0)
    drop, rise = finite & (safe < 0), finite & (safe >= 0)
    rgba[drop, :3] = _DROP_RGB
    rgba[rise, :3] = _RISE_RGB
    lo, hi = _DELTA_ALPHA
    strength = np.clip(np.abs(safe) / _DELTA_FULL_DB, 0.0, 1.0)
    rgba[..., 3] = np.where(finite, np.rint(lo + (hi - lo) * strength), 0).astype("uint8")


def _paint_backscatter(img: np.ndarray, rgba: np.ndarray, vmin, vmax) -> None:
    finite = np.isfinite(img)
    if vmin is None or vmax is None:
        sample = img[finite]
        if sample.size:
            lo, hi = np.percentile(sample, _DEFAULT_PERCENTILES)
        else:
            lo, hi = -25.0, 0.0
        vmin = lo if vmin is None else vmin
        vmax = hi if vmax is None else vmax
    span = max(float(vmax) - float(vmin), 1e-9)
    grey = np.clip((np.where(finite, img, vmin) - vmin) / span, 0.0, 1.0)
    level = np.rint(grey * 255).astype("uint8")
    rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = level
    rgba[..., 3] = np.where(finite, 255, 0).astype("uint8")


def render_png(values, grid: Grid, kind: str, vmin: float | None = None, vmax: float | None = None):
    """Render a block-grid array as a transparent PNG draped on Web Mercator.

    `values` is shaped `grid.shape` with NaN where there is nothing to show. `kind` picks the
    colouring: "delta" (change in dB: red drop, blue rise, opacity grows with size), "agreement"
    (codes AGREE_L / AGREE_BOTH / AGREE_C in the three brand colours) or "backscatter" (dB as
    grey; pass the same `vmin`/`vmax` for before and after so they share one stretch).

    Returns `(png_bytes, bounds)`, with `bounds` = [[lon, lat] UL, UR, LR, LL] of the image.
    The image is at most 2048 px on its longest side.
    """
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
    values = np.asarray(values, dtype="float64")
    if values.shape != grid.shape:
        raise ValueError(f"values must match the grid shape {grid.shape}, got {values.shape}")
    img, extent = _warp_to_mercator(values, grid)
    rgba = np.zeros((*img.shape, 4), dtype="uint8")
    if kind == "agreement":
        _paint_agreement(img, rgba)
    elif kind == "delta":
        _paint_delta(img, rgba)
    else:
        _paint_backscatter(img, rgba, vmin, vmax)
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, format="PNG", optimize=True)
    return buf.getvalue(), _mercator_bounds_lonlat(extent)

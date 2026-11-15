"""Change areas: connected changed blocks become polygons.

Blocks flagged as changed by NISAR (L) or Sentinel-1 (C) are merged, grouped into 4-connected
patches, and each patch of at least `min_ha` hectares becomes one area. A patch is labelled by
which sensor flagged the majority of its blocks. Polygons are GeoJSON in lon/lat (EPSG:4326).
"""

from __future__ import annotations

import numpy as np
import shapely
from pyproj import Transformer
from scipy import ndimage
from shapely.geometry import box as shapely_box
from shapely.geometry import mapping
from shapely.ops import unary_union

from .types import Grid

_FOUR_CONNECTED = ndimage.generate_binary_structure(2, 1)  # corners alone do not connect blocks
_COORD_DIGITS = 6  # about 0.1 m in lon/lat


def _agreement(l_blocks: int, c_blocks: int, total: int) -> str:
    """ "L" or "C" when only that sensor flagged a majority of the blocks, else "both".

    A majority is more than half of the patch's blocks. When both sensors flagged more than half
    (they overlap) or neither did (they split the patch evenly), both sensors saw the area.
    """
    l_major, c_major = l_blocks * 2 > total, c_blocks * 2 > total
    if l_major and not c_major:
        return "L"
    if c_major and not l_major:
        return "C"
    return "both"


def _round_coords(obj):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(v), _COORD_DIGITS) for v in obj]
        return [_round_coords(o) for o in obj]
    return obj


def _block_polygon(block_mask: np.ndarray, grid: Grid, to_lonlat: Transformer) -> dict:
    """Union of the mask's blocks as a GeoJSON geometry in lon/lat."""
    rows, cols = np.nonzero(block_mask)
    squares = []
    for r, c in zip(rows.tolist(), cols.tolist()):
        x0 = grid.xmin + c * grid.res
        y1 = grid.ymax - r * grid.res
        squares.append(shapely_box(x0, y1 - grid.res, x0 + grid.res, y1))
    merged = unary_union(squares)
    lonlat = shapely.transform(
        merged, lambda xy: np.column_stack(to_lonlat.transform(xy[:, 0], xy[:, 1]))
    )
    geometry = mapping(lonlat)
    return {"type": geometry["type"], "coordinates": _round_coords(geometry["coordinates"])}


def label_areas(changed_L, changed_C, grid: Grid, min_ha: float = 3):
    """Group changed blocks into areas of at least `min_ha` hectares.

    `changed_L` and `changed_C` are boolean block arrays shaped `grid.shape` (NISAR and Sentinel-1
    "changed" masks). Returns a list of `(geometry, block_mask, agreement)`, largest area first:
    a GeoJSON Polygon/MultiPolygon in lon/lat, a boolean array shaped `grid.shape` marking the
    area's blocks, and "L", "C" or "both".
    """
    l_mask, c_mask = np.asarray(changed_L, dtype=bool), np.asarray(changed_C, dtype=bool)
    if l_mask.shape != grid.shape or c_mask.shape != grid.shape:
        raise ValueError(
            f"masks must match the grid shape {grid.shape}, got {l_mask.shape} and {c_mask.shape}"
        )
    block_ha = grid.res * grid.res / 10_000.0
    labels, count = ndimage.label(l_mask | c_mask, structure=_FOUR_CONNECTED)
    found = []
    for idx in range(1, count + 1):
        block_mask = labels == idx
        n = int(block_mask.sum())
        if n * block_ha + 1e-9 < min_ha:
            continue
        agreement = _agreement(
            int((block_mask & l_mask).sum()), int((block_mask & c_mask).sum()), n
        )
        found.append((n, block_mask, agreement))
    if not found:
        return []
    to_lonlat = Transformer.from_crs(grid.epsg, 4326, always_xy=True)
    found.sort(key=lambda f: -f[0])  # stable: equal sizes keep scan order
    return [(_block_polygon(m, grid, to_lonlat), m, a) for _, m, a in found]

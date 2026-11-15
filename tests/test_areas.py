"""Change areas: connected blocks, the 3 ha minimum, agreement by majority, GeoJSON in lon/lat."""

import numpy as np
import pytest
from pyproj import Transformer
from shapely.geometry import shape

from sarstellar.areas import label_areas
from sarstellar.grid import grid_for_bbox

GRID = grid_for_bbox([-121.0, 37.0, -120.97, 37.03], 32610)  # about 2.7 x 3.3 km of 100 m blocks


def empty():
    return np.zeros(GRID.shape, dtype=bool)


def blob(mask, r0, c0, h, w):
    mask[r0 : r0 + h, c0 : c0 + w] = True
    return mask


def test_min_area():
    changed = empty()
    blob(changed, 2, 2, 1, 2)  # two blocks = 2 ha: dropped
    blob(changed, 10, 10, 1, 3)  # three blocks = 3 ha: kept
    areas = label_areas(changed, empty(), GRID)
    assert len(areas) == 1
    geometry, block_mask, agreement = areas[0]
    assert block_mask.sum() == 3
    assert block_mask[10, 10:13].all()
    assert agreement == "L"
    assert shape(geometry).geom_type == "Polygon"


def test_min_area_is_configurable():
    changed = empty()
    blob(changed, 2, 2, 1, 2)
    assert len(label_areas(changed, empty(), GRID, min_ha=2)) == 1
    assert label_areas(changed, empty(), GRID, min_ha=5) == []


def test_agreement_majority():
    # nine blocks: L saw all of them, C saw only two (a minority) -> "L"
    l, c = empty(), empty()
    blob(l, 5, 5, 3, 3)
    c[5, 5] = c[5, 6] = True
    assert label_areas(l, c, GRID)[0][2] == "L"
    # C saw seven of nine, L saw all -> both sensors saw most of it -> "both"
    c = blob(empty(), 5, 5, 3, 3)
    c[7, 5:8] = False
    assert label_areas(l, c, GRID)[0][2] == "both"
    # only C -> "C"
    assert label_areas(empty(), blob(empty(), 5, 5, 3, 3), GRID)[0][2] == "C"


def test_adjacent_l_and_c_blocks_merge_into_one_area():
    l, c = empty(), empty()
    blob(l, 4, 4, 1, 3)  # three L-only blocks
    blob(c, 4, 7, 1, 4)  # four C-only blocks right next to them
    areas = label_areas(l, c, GRID)
    assert len(areas) == 1
    _, block_mask, agreement = areas[0]
    assert block_mask.sum() == 7
    # L saw 3/7 and C saw 4/7: C has the majority, L does not
    assert agreement == "C"


def test_split_area_with_no_majority_for_either_sensor_is_both():
    l, c = empty(), empty()
    blob(l, 4, 4, 1, 3)
    blob(c, 4, 7, 1, 3)  # 3 L-only + 3 C-only: each sensor saw exactly half
    areas = label_areas(l, c, GRID)
    assert len(areas) == 1
    assert areas[0][2] == "both"


def test_diagonal_blocks_are_separate_areas():
    changed = empty()
    blob(changed, 4, 4, 1, 3)
    blob(changed, 5, 7, 1, 3)  # touches the first only at a corner
    assert len(label_areas(changed, empty(), GRID)) == 2


def test_areas_are_sorted_largest_first():
    changed = empty()
    blob(changed, 2, 2, 1, 3)
    blob(changed, 10, 10, 3, 3)
    areas = label_areas(changed, empty(), GRID)
    assert [a[1].sum() for a in areas] == [9, 3]


def test_geometry_is_geojson_in_lon_lat_over_the_right_place():
    changed = blob(empty(), 4, 6, 2, 3)  # six blocks
    geometry, _, _ = label_areas(changed, empty(), GRID)[0]
    assert geometry["type"] == "Polygon"
    poly = shape(geometry)
    assert poly.is_valid
    minx, miny, maxx, maxy = poly.bounds
    assert -121.0 <= minx < maxx <= -120.96
    assert 37.0 <= miny < maxy <= 37.04
    # area of the polygon in UTM metres is 6 blocks x 1 ha
    to_utm = Transformer.from_crs(4326, 32610, always_xy=True)
    xs, ys = to_utm.transform(*zip(*geometry["coordinates"][0]))
    ring = shape({"type": "Polygon", "coordinates": [list(zip(xs, ys))]})
    assert ring.area == pytest.approx(6 * 10_000.0, rel=1e-3)
    # the polygon's north edge is the grid row 4 line
    assert max(ys) == pytest.approx(GRID.ymax - 4 * GRID.res, abs=1.0)


def test_area_with_a_hole_keeps_the_hole():
    changed = blob(empty(), 5, 5, 5, 5)
    changed[7, 7] = False  # a hole in the middle (the hole is not a separate area: 1 block < 3 ha)
    geometry, block_mask, _ = label_areas(changed, empty(), GRID)[0]
    assert len(geometry["coordinates"]) == 2  # shell + one interior ring
    assert block_mask.sum() == 24


def test_no_change_gives_no_areas():
    assert label_areas(empty(), empty(), GRID) == []


def test_nan_in_a_float_mask_means_no_change_not_change():
    # a float mask with NaN for "no data" must not turn every NaN cell into a changed block
    l_float = np.full(GRID.shape, np.nan)
    l_float[10, 10:13] = 1.0
    l_float[20, 20:25] = 0.0
    areas = label_areas(l_float, np.full(GRID.shape, np.nan), GRID)
    assert len(areas) == 1
    assert areas[0][1].sum() == 3
    assert areas[0][2] == "L"


def test_shape_mismatch_raises():
    with pytest.raises(ValueError):
        label_areas(np.zeros((3, 3), bool), empty(), GRID)

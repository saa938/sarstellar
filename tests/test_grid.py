"""Grid snapping, validity masks, block averaging and reprojection onto the 1-ha block grid."""

import numpy as np
import pytest
from pyproj import Transformer

from sarstellar.grid import (
    block_mean,
    block_valid_frac,
    grid_for_bbox,
    lonlat_corners,
    to_grid,
    valid_mask,
)
from sarstellar.types import Grid


def _projected_boundary(bbox, epsg, n=50):
    """Points along the lon/lat box boundary, in projected metres (an independent check)."""
    w, s, e, nn = bbox
    t = np.linspace(0.0, 1.0, n)
    lons = np.concatenate([w + (e - w) * t, w + (e - w) * t, np.full(n, w), np.full(n, e)])
    lats = np.concatenate([np.full(n, s), np.full(n, nn), s + (nn - s) * t, s + (nn - s) * t])
    return Transformer.from_crs(4326, epsg, always_xy=True).transform(lons, lats)


# --- block_mean / valid_mask -------------------------------------------------------------------


def test_block_mean_masks():
    a = np.ones((4, 4))
    valid = np.ones((4, 4), bool)
    valid[:2, :2] = False  # one whole quadrant invalid
    out = block_mean(a, valid, block=2, min_valid_frac=1.0)
    assert out.shape == (2, 2)
    assert np.isnan(out[0, 0])
    assert np.allclose([out[0, 1], out[1, 0], out[1, 1]], 1.0)


def test_block_mean_averages_only_valid_pixels_and_applies_threshold():
    a = np.array([[1.0, 3.0, 5.0, 100.0], [7.0, 100.0, 5.0, 100.0]])
    valid = np.array([[1, 1, 1, 0], [1, 0, 0, 0]], bool)
    # block 0 has 3 of 4 valid (1, 3, 7); block 1 has 1 of 4 valid (5)
    out = block_mean(a, valid, block=2)  # default min_valid_frac 0.5
    assert out[0, 0] == pytest.approx((1 + 3 + 7) / 3)
    assert np.isnan(out[0, 1])
    # exactly half valid is enough (>= 50%)
    half = np.array([[1, 1, 0, 0], [0, 0, 0, 0]], bool)
    assert block_mean(a, half, block=2, min_valid_frac=0.5)[0, 0] == pytest.approx(2.0)


def test_block_mean_ignores_invalid_nan_and_trims_partial_blocks():
    a = np.full((5, 7), 2.0)
    a[0, 0] = np.nan  # NaN under an invalid flag must not poison the mean
    valid = np.ones((5, 7), bool)
    valid[0, 0] = False
    out = block_mean(a, valid, block=2)
    assert out.shape == (2, 3)  # the ragged last row/column are dropped
    assert np.allclose(out, 2.0)


def test_block_mean_sample_uses_sampled_pixels_as_denominator():
    a = np.full((10, 10), 4.0)
    valid = np.ones((10, 10), bool)
    sample = np.zeros((10, 10), bool)
    sample[::3, ::3] = True  # 16 sampled pixels
    # 16 of 100 pixels is far below 50%, but every sampled pixel is valid
    assert block_mean(a, valid, block=10, sample=sample)[0, 0] == pytest.approx(4.0)
    valid[::3, ::3] = False
    assert np.isnan(block_mean(a, valid, block=10, sample=sample)[0, 0])


def test_block_valid_frac():
    valid = np.zeros((4, 4), bool)
    valid[:2, :2] = True  # block (0, 0) fully valid
    valid[2, 2] = True  # block (1, 1) one of four
    out = block_valid_frac(valid, block=2)
    assert out.tolist() == [[1.0, 0.0], [0.0, 0.25]]


def test_valid_mask_rules():
    mask = np.array([[0, 1, 254, 255]], dtype=np.uint8)
    ok = np.ones((1, 4), "f4")
    assert valid_mask(mask, ok).tolist() == [[False, True, True, False]]
    # value rule: finite and strictly positive, for every array passed
    hh = np.array([[1.0, np.nan, 0.0, 1.0]], "f4")
    hv = np.array([[1.0, 1.0, 1.0, -1.0]], "f4")
    all_ones = np.full((1, 4), 5, np.uint8)
    assert valid_mask(all_ones, hh, hv).tolist() == [[True, False, False, False]]
    assert valid_mask(all_ones).tolist() == [[True, True, True, True]]


# --- grid_for_bbox / lonlat_corners -------------------------------------------------------------


def test_grid_snaps_100m():
    bbox = (-119.3705, 48.0531, -118.7196, 48.3605)  # the Kaiser box; zone 10 file, zone 11 site
    g = grid_for_bbox(bbox, 32610)
    assert isinstance(g, Grid) and g.epsg == 32610 and g.res == 100.0
    for v in (g.xmin, g.xmax, g.ymin, g.ymax):
        assert v % 100 == 0
    ny, nx = g.shape
    assert ny * 100 == g.ymax - g.ymin and nx * 100 == g.xmax - g.xmin
    xs, ys = _projected_boundary(bbox, 32610)
    # snapped outward: contains the whole box, and by less than one block of slack per side
    assert g.xmin <= min(xs) < g.xmin + 100 and max(xs) <= g.xmax < max(xs) + 100
    assert g.ymin <= min(ys) < g.ymin + 100 and max(ys) <= g.ymax < max(ys) + 100


def test_grid_for_bbox_rejects_empty_box():
    with pytest.raises(ValueError):
        grid_for_bbox((-119.0, 48.0, -119.5, 48.1), 32610)
    with pytest.raises(ValueError):
        grid_for_bbox((-119.5, 48.1, -119.0, 48.0), 32610)


def test_utm_zone_straddle():
    # lon -120 is the zone 10 / 11 boundary. Each file's EPSG gets its own grid for the same box.
    bbox = (-120.05, 46.95, -119.95, 47.05)
    grids = {epsg: grid_for_bbox(bbox, epsg) for epsg in (32610, 32611)}
    assert grids[32610] != grids[32611]
    w, s, e, n = bbox
    for epsg, g in grids.items():
        corners = lonlat_corners(g)
        lons = [c[0] for c in corners]
        lats = [c[1] for c in corners]
        assert min(lons) <= w and max(lons) >= e, epsg
        assert min(lats) <= s and max(lats) >= n, epsg
        # and in projected space, where the grid really is a rectangle
        xs, ys = _projected_boundary(bbox, epsg)
        assert g.xmin <= min(xs) and max(xs) <= g.xmax, epsg
        assert g.ymin <= min(ys) and max(ys) <= g.ymax, epsg


def test_lonlat_corners_order_is_ul_ur_lr_ll():
    g = Grid(epsg=32610, xmin=500000.0, xmax=500200.0, ymin=5200000.0, ymax=5200300.0)
    ul, ur, lr, ll = lonlat_corners(g)
    assert ul[0] == pytest.approx(-123.0, abs=1e-5)  # x = 500000 is the zone 10 central meridian
    assert ur[0] > ul[0] and lr[0] > ll[0]
    assert ul[1] > ll[1] and ur[1] > lr[1]
    assert all(len(c) == 2 for c in (ul, ur, lr, ll))


# --- to_grid -----------------------------------------------------------------------------------


def test_to_grid_averages_to_blocks_and_skips_nan():
    from rasterio.transform import from_origin

    g = Grid(epsg=32610, xmin=500000.0, xmax=500200.0, ymin=5200000.0, ymax=5200200.0)
    src = np.arange(20 * 20, dtype="float64").reshape(20, 20)  # 10 m pixels covering the grid
    src[:10, :10] = np.nan  # the whole upper-left block has no data
    out = to_grid(src, from_origin(500000.0, 5200200.0, 10.0, 10.0), "EPSG:32610", g)
    assert out.shape == (2, 2)
    assert np.isnan(out[0, 0])
    assert out[0, 1] == pytest.approx(src[:10, 10:].mean())
    assert out[1, 0] == pytest.approx(src[10:, :10].mean())
    assert out[1, 1] == pytest.approx(src[10:, 10:].mean())


def test_to_grid_reprojects_across_utm_zones():
    from rasterio.transform import from_origin
    from rasterio.warp import transform_bounds

    bbox = (-120.05, 46.95, -119.95, 47.05)
    g = grid_for_bbox(bbox, 32610)
    # a Sentinel-1 style raster in the neighbouring zone, 30 m pixels, bigger than the grid
    left, bottom, right, top = transform_bounds(
        "EPSG:32610", "EPSG:32611", g.xmin, g.ymin, g.xmax, g.ymax
    )
    left, top = np.floor(left / 30) * 30 - 600, np.ceil(top / 30) * 30 + 600
    ncols = int((right + 600 - left) / 30) + 1
    nrows = int((top - (bottom - 600)) / 30) + 1
    src = np.full((nrows, ncols), 3.0)
    out = to_grid(src, from_origin(left, top, 30.0, 30.0), 32611, g)
    assert out.shape == g.shape
    assert np.allclose(out, 3.0)


def test_to_grid_leaves_uncovered_blocks_nan():
    from rasterio.transform import from_origin

    g = Grid(epsg=32610, xmin=500000.0, xmax=500300.0, ymin=5200000.0, ymax=5200300.0)
    src = np.ones((10, 10))  # covers only the lower-left block
    out = to_grid(src, from_origin(500000.0, 5200100.0, 10.0, 10.0), "EPSG:32610", g)
    assert out[2, 0] == pytest.approx(1.0)
    # Blocks a full block or more away from the source are NaN. (A block that only touches the
    # source's edge can pick up the edge pixel: GDAL's average kernel is not strict there.)
    assert np.isnan(out[0, :]).all() and np.isnan(out[:, 2]).all()

"""Overlay PNGs: Web-Mercator reprojection, transparent NaN, brand colours, size cap."""

import io

import numpy as np
import pytest
from PIL import Image

from sarstellar.grid import grid_for_bbox, lonlat_corners
from sarstellar.render import AGREE_BOTH, AGREE_C, AGREE_L, render_png
from sarstellar.types import Grid

GRID = grid_for_bbox([-121.0, 37.0, -120.95, 37.05], 32610)  # about 4.4 x 5.6 km


def decode(png: bytes) -> np.ndarray:
    return np.array(Image.open(io.BytesIO(png)).convert("RGBA"))


def nan_grid(grid=GRID):
    return np.full(grid.shape, np.nan)


def test_png_is_valid_and_bounds_are_ul_ur_lr_ll():
    values = nan_grid()
    values[5:10, 5:10] = -4.0
    png, bounds = render_png(values, GRID, "delta")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    img = Image.open(io.BytesIO(png))
    assert img.mode == "RGBA"
    (ul, ur, lr, ll) = bounds
    assert len(bounds) == 4 and all(len(p) == 2 for p in bounds)
    assert ul[0] < ur[0] and ll[0] < lr[0]  # west before east
    assert ul[1] > ll[1] and ur[1] > lr[1]  # north above south
    assert ul[1] == pytest.approx(ur[1]) and ll[1] == pytest.approx(
        lr[1]
    )  # Mercator is axis-aligned
    # the Web-Mercator extent encloses the box the grid was snapped to
    west, south, east, north = -121.0, 37.0, -120.95, 37.05
    assert ul[0] <= west and lr[0] >= east and ul[1] >= north and ll[1] <= south


def test_bounds_enclose_the_utm_grid_corners():
    _, bounds = render_png(nan_grid(), GRID, "delta")
    for lon, lat in lonlat_corners(GRID):
        assert bounds[0][0] - 1e-6 <= lon <= bounds[1][0] + 1e-6
        assert bounds[3][1] - 1e-6 <= lat <= bounds[0][1] + 1e-6


def test_nan_is_transparent():
    values = nan_grid()
    values[10:20, 10:20] = 3.0
    png, _ = render_png(values, GRID, "delta")
    rgba = decode(png)
    assert rgba[..., 3].min() == 0  # NaN cells (and the area outside the UTM footprint)
    assert rgba[..., 3].max() > 0
    # a fully-NaN input is a fully transparent image, not an error
    blank = decode(render_png(nan_grid(), GRID, "backscatter")[0])
    assert blank[..., 3].max() == 0


def test_agreement_uses_only_the_three_brand_colours():
    values = nan_grid()
    values[5:15, 5:15] = AGREE_L
    values[20:30, 5:15] = AGREE_BOTH
    values[35:45, 5:15] = AGREE_C
    rgba = decode(render_png(values, GRID, "agreement")[0])
    visible = rgba[rgba[..., 3] > 0][:, :3]
    colours = {tuple(int(v) for v in px) for px in np.unique(visible, axis=0)}
    assert colours == {(0xF5, 0x9E, 0x0B), (0xA7, 0x8B, 0xFA), (0x22, 0xD3, 0xEE)}
    assert (AGREE_L, AGREE_BOTH, AGREE_C) == (1, 2, 3)


def test_agreement_blocks_land_in_the_right_place():
    values = nan_grid()
    values[0:6, 0:6] = AGREE_L  # north-west corner of the grid
    values[-6:, -6:] = AGREE_C  # south-east corner
    rgba = decode(render_png(values, GRID, "agreement")[0])
    h, w = rgba.shape[:2]
    # amber (NISAR only) is in the upper-left half, cyan (Sentinel-1 only) in the lower-right half
    amber = np.argwhere((rgba[..., 0] == 0xF5) & (rgba[..., 2] == 0x0B) & (rgba[..., 3] > 0))
    cyan = np.argwhere((rgba[..., 0] == 0x22) & (rgba[..., 2] == 0xEE) & (rgba[..., 3] > 0))
    assert len(amber) and len(cyan)
    assert amber[:, 0].mean() < h / 2 and amber[:, 1].mean() < w / 2
    assert cyan[:, 0].mean() > h / 2 and cyan[:, 1].mean() > w / 2


def test_agreement_ignores_codes_outside_1_to_3():
    values = nan_grid()
    values[5:15, 5:15] = 0.0
    values[20:30, 5:15] = 7.0
    assert decode(render_png(values, GRID, "agreement")[0])[..., 3].max() == 0


def test_delta_drop_is_red_and_rise_is_blue_and_both_avoid_brand_colours():
    values = nan_grid()
    values[5:15, 5:15] = -6.0
    values[20:30, 5:15] = 6.0
    rgba = decode(render_png(values, GRID, "delta")[0])
    visible = rgba[rgba[..., 3] > 0]
    red = visible[(visible[:, 0] > visible[:, 2]) & (visible[:, 0] > 150)]
    blue = visible[(visible[:, 2] > visible[:, 0]) & (visible[:, 2] > 150)]
    assert len(red) and len(blue)
    brand = {(0xF5, 0x9E, 0x0B), (0xA7, 0x8B, 0xFA), (0x22, 0xD3, 0xEE)}
    assert not brand & {tuple(int(v) for v in px[:3]) for px in visible}


def test_delta_magnitude_sets_opacity():
    values = nan_grid()
    values[5:15, 5:15] = -0.5
    values[20:30, 5:15] = -6.0
    rgba = decode(render_png(values, GRID, "delta")[0])
    alphas = rgba[..., 3][rgba[..., 3] > 0]
    assert alphas.min() < alphas.max()


def test_backscatter_is_grey_and_respects_shared_stretch():
    values = nan_grid()
    values[5:15, 5:15] = -20.0
    values[20:30, 5:15] = -8.0
    rgba = decode(render_png(values, GRID, "backscatter", vmin=-25.0, vmax=0.0)[0])
    visible = rgba[rgba[..., 3] > 0]
    assert (visible[:, 0] == visible[:, 1]).all() and (visible[:, 1] == visible[:, 2]).all()
    assert (visible[:, 3] == 255).all()
    levels = sorted({int(v) for v in visible[:, 0]})
    assert len(levels) == 2 and levels[0] < levels[1]  # brighter radar return -> lighter grey
    # same data, different stretch -> different grey
    other = decode(render_png(values, GRID, "backscatter", vmin=-40.0, vmax=-5.0)[0])
    assert not np.array_equal(rgba, other)


def test_size_is_capped_at_2048_px():
    big = Grid(epsg=32610, xmin=500_000.0, xmax=540_000.0, ymin=4_100_000.0, ymax=4_140_000.0)
    assert big.shape == (400, 400)
    values = np.full(big.shape, -3.0)
    png, _ = render_png(values, big, "delta")
    w, h = Image.open(io.BytesIO(png)).size
    assert max(w, h) <= 2048
    assert max(w, h) > 1000  # still sharp enough to show 1 ha blocks


def test_small_grids_are_upsampled_so_blocks_stay_crisp():
    png, _ = render_png(nan_grid(), GRID, "delta")
    w, h = Image.open(io.BytesIO(png)).size
    ny, nx = GRID.shape
    assert w >= 3 * nx and h >= 3 * ny


def test_bad_inputs():
    with pytest.raises(ValueError):
        render_png(nan_grid(), GRID, "heatmap")
    with pytest.raises(ValueError):
        render_png(np.zeros((3, 3)), GRID, "delta")

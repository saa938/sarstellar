"""Reference-label rasters: optical disturbance alerts, water maps, crop maps, fire perimeters.

The pure logic is tested on small synthetic rasters. Network loaders are tested with their
network call replaced; one live test per source (run with `-m live`) hits the real service.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from rasterio.transform import from_origin

from sarstellar import refs_scoring as rs
from sarstellar.types import Grid

# 18 x 18 blocks of 100 m in UTM 10N. A synthetic 30 m source raster (60 x 60 px = 1.8 km)
# on the same lattice: 10 source pixels = 300 m = 3 blocks, so blocks line up with pixels.
GRID = Grid(epsg=32610, xmin=500000.0, xmax=501800.0, ymin=5000000.0, ymax=5001800.0, res=100.0)
SRC_TRANSFORM = from_origin(500000.0, 5001800.0, 30.0, 30.0)
CRS = "EPSG:32610"

EPOCH = date(2020, 12, 31)


def days(d: date) -> int:
    return (d - EPOCH).days


# --- OPERA DIST-ALERT-HLS ------------------------------------------------------------------------


def test_dist_loss_indicator_applies_every_rule():
    start, end = date(2026, 6, 1), date(2026, 9, 30)
    inside, before, after = (
        days(date(2026, 7, 15)),
        days(date(2026, 5, 31)),
        days(date(2026, 10, 1)),
    )
    status = np.array([6, 6, 6, 6, 1, 4, 3, 0, 255, 5])
    when = np.array([inside, before, after, inside, inside, inside, inside, inside, inside, -1])
    anom = np.array([80, 80, 80, 49, 90, 90, 100, 90, 90, 90])
    got = rs.dist_loss_indicator(status, when, anom, start, end)
    # 0: all rules met. 1: dated before the window. 2: after it. 3: loss under 50%.
    # 4, 5: first-detection statuses are not confirmed. 6: status 3 with anomaly 100 counts.
    # 7: status 0 (no disturbance). 8: status 255 is no data. 9: no date.
    assert got[:8].tolist() == [1, 0, 0, 0, 0, 0, 1, 0]
    assert np.isnan(got[8])
    assert got[9] == 0.0  # status 5 with a missing date is not inside any window


def test_dist_loss_indicator_window_ends_are_inclusive():
    start, end = date(2026, 6, 1), date(2026, 9, 30)
    status = np.array([6, 6])
    when = np.array([days(start), days(end)])
    got = rs.dist_loss_indicator(status, when, np.array([60, 60]), start, end)
    assert got.tolist() == [1.0, 1.0]


def test_dist_layers_to_grid_gives_loss_fraction_per_block():
    status = np.zeros((60, 60), dtype="uint8")
    when = np.full((60, 60), -1, dtype="int16")
    anom = np.zeros((60, 60), dtype="uint8")
    # A 10 x 10 pixel disturbance in the top-left corner covers blocks (0..2, 0..2) fully,
    # and half of the pixels of blocks in a 5-pixel strip beside it.
    status[:10, :10] = 6
    when[:10, :10] = days(date(2026, 7, 1))
    anom[:10, :10] = 90
    got = rs.dist_layers_to_grid(
        status, when, anom, SRC_TRANSFORM, CRS, GRID, date(2026, 6, 1), date(2026, 9, 30)
    )
    assert got.shape == GRID.shape
    assert np.allclose(got[:3, :3], 1.0)
    assert np.allclose(got[3:, :], 0.0) and np.allclose(got[:, 3:], 0.0)


def test_dist_layers_to_grid_marks_uncovered_blocks_nan():
    status = np.full((20, 20), 255, dtype="uint8")  # no data anywhere in the source
    when = np.full((20, 20), -1, dtype="int16")
    anom = np.zeros((20, 20), dtype="uint8")
    got = rs.dist_layers_to_grid(
        status, when, anom, SRC_TRANSFORM, CRS, GRID, date(2026, 6, 1), date(2026, 9, 30)
    )
    assert np.isnan(got).all()


def test_pick_dist_granules_takes_latest_per_tile_not_before_the_window_end():
    items = [
        _dist_item("T10TES", "20260915T185602Z"),
        _dist_item("T10TES", "20261005T185602Z"),
        _dist_item("T10TES", "20261011T185602Z"),
        _dist_item("T10TES", "20261201T185602Z"),  # beyond the lag: never used
        _dist_item("T10TFS", "20261008T185602Z"),
        _dist_item("T10TGS", "20260920T185602Z"),  # before the window end: never used
    ]
    picked = rs.pick_dist_granules(items, end=date(2026, 9, 30), lag_days=30)
    assert {p["tile"]: p["acquired"] for p in picked} == {
        "T10TES": date(2026, 10, 11),
        "T10TFS": date(2026, 10, 8),
    }
    assert set(picked[0]["urls"]) == {"status", "date", "anom"}


def _dist_item(tile: str, stamp: str) -> dict:
    base = f"OPERA_L3_DIST-ALERT-HLS_{tile}_{stamp}_20261101T000000Z_S2A_30_v1"
    url = f"https://example.test/{base}/{base}_"
    return {
        "umm": {
            "GranuleUR": base,
            "RelatedUrls": [
                {"Type": "GET DATA", "URL": url + f"{layer}.tif"}
                for layer in ("VEG-DIST-STATUS", "VEG-DIST-DATE", "VEG-ANOM-MAX", "VEG-IND")
            ],
        }
    }


# --- OPERA DSWx ----------------------------------------------------------------------------------


def test_water_indicator_counts_water_classes_and_masks_the_rest():
    wtr = np.array([0, 1, 2, 3, 252, 253, 254, 255])
    got = rs.water_indicator(wtr)
    assert got[:4].tolist() == [0.0, 1.0, 1.0, 1.0]
    assert np.isnan(got[4:]).all()
    assert rs.water_indicator(wtr, classes=(1,))[:4].tolist() == [0.0, 1.0, 0.0, 0.0]


def test_water_layers_to_grid_fraction_and_cloud_gap():
    wtr = np.zeros((60, 60), dtype="uint8")
    wtr[:10, :10] = 1  # open water over blocks (0..2, 0..2)
    wtr[30:60, 30:60] = 253  # a cloud over blocks (9..17, 9..17)
    got = rs.water_layers_to_grid(wtr, SRC_TRANSFORM, CRS, GRID)
    assert np.allclose(got[:3, :3], 1.0)
    assert np.allclose(got[3:9, 3:9], 0.0)
    assert np.isnan(got[9:, 9:]).all()


def test_pick_dswx_granules_nearest_first_within_the_window():
    items = [
        _dswx_item("DSWx-S1", "T15RVP", "20260913T001747Z"),
        _dswx_item("DSWx-S1", "T15RVP", "20260918T001747Z"),  # 5 days: outside +-3
        _dswx_item("DSWx-S1", "T15RUP", "20260911T122224Z"),
        _dswx_item("DSWx-S1", "T15RVP", "20260915T001747Z"),
    ]
    picked = rs.pick_dswx_granules(items, when=date(2026, 9, 13), max_days=3)
    assert [(p["tile"], p["acquired"]) for p in picked] == [
        ("T15RVP", date(2026, 9, 13)),
        ("T15RUP", date(2026, 9, 11)),
        ("T15RVP", date(2026, 9, 15)),
    ]
    assert picked[0]["url"].endswith("_B01_WTR.tif")


def _dswx_item(product: str, tile: str, stamp: str) -> dict:
    base = f"OPERA_L3_{product}_{tile}_{stamp}_20261012T045909Z_S1D_30_v1.0"
    return {
        "umm": {
            "GranuleUR": base,
            "RelatedUrls": [
                {"Type": "GET DATA", "URL": f"https://example.test/{base}_{band}.tif"}
                for band in ("B01_WTR", "B02_BWTR", "B03_CONF")
            ],
        }
    }


def test_dswx_water_prefers_sentinel1_then_fills_gaps_from_hls(monkeypatch):
    s1 = np.full(GRID.shape, np.nan)
    s1[:9, :] = 0.0
    s1[:2, :2] = 1.0
    hls = np.full(GRID.shape, 0.5)

    def fake(product, grid, when, max_days, fs):
        return s1 if product == "S1" else hls

    monkeypatch.setattr(rs, "_dswx_product_water", fake)
    got = rs.dswx_water(GRID, date(2026, 9, 13), fs=object())
    assert got[0, 0] == 1.0 and got[5, 5] == 0.0  # Sentinel-1 wins where it has data
    assert np.allclose(got[9:, :], 0.5)  # HLS fills the rest


# --- CDL -----------------------------------------------------------------------------------------


def test_cdl_cultivated_indicator():
    cdl = np.array([0, 1, 5, 24, 36, 61, 62, 63, 81, 111, 121, 141, 176, 190, 204, 227, 250])
    got = rs.cdl_cultivated_indicator(cdl)
    crop = {1, 5, 24, 36, 61, 204, 227, 250}
    for value, flag in zip(cdl, got, strict=True):
        if value in (0, 81):  # background and clouds/no data
            assert np.isnan(flag)
        else:
            assert flag == (1.0 if value in crop else 0.0), value


def test_cdl_crop_is_true_where_half_the_block_is_cultivated(monkeypatch):
    cdl = np.full((60, 60), 176, dtype="uint8")  # grass/pasture
    cdl[:, :30] = 1  # left half corn
    cdl[:10, 30:40] = 5  # a small soybean patch beside it

    monkeypatch.setattr(rs, "fetch_cdl", lambda grid, year=None: (cdl, SRC_TRANSFORM, CRS, 2025))
    got = rs.cdl_crop(GRID)
    assert got.dtype == bool and got.shape == GRID.shape
    assert got[:, :9].all()  # corn half: pixel columns 0..29 are block columns 0..8
    assert got[:3, 9:12].all()  # the soybean patch: block rows 0..2, columns 9..11
    assert not got[3:, 9:].any() and not got[:, 12:].any()  # grass stays False


def test_cdl_years_to_try_starts_this_year_and_walks_back():
    assert rs.cdl_years_to_try(None, today=date(2026, 11, 14))[:3] == [2026, 2025, 2024]
    assert rs.cdl_years_to_try(2023, today=date(2026, 11, 14)) == [2023]


def test_fetch_cdl_uses_latest_year_the_service_has(monkeypatch):
    calls = []

    def fake_wcs(coverage, bounds, res):
        calls.append(coverage)
        if coverage == "cdl_2026":
            return None  # not published yet: the service answers with an XML error
        return np.full((4, 4), 1, dtype="uint8"), from_origin(0, 120, 30, 30), "EPSG:5070"

    monkeypatch.setattr(rs, "_wcs_get_coverage", fake_wcs)
    _arr, _t, crs, year = rs.fetch_cdl(GRID)
    assert year == 2025 and calls == ["cdl_2026", "cdl_2025"] and crs == "EPSG:5070"


# --- NIFC perimeters -----------------------------------------------------------------------------


def _lonlat_box(x0, y0, x1, y1, epsg=32610):
    from pyproj import Transformer

    t = Transformer.from_crs(epsg, 4326, always_xy=True)
    pts = [t.transform(x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))]
    return [list(p) for p in pts]


def test_nifc_mask_marks_blocks_whose_centre_is_inside():
    # Covers x 500000..500500 and y 5001300..5001800: blocks rows 0..4, cols 0..4.
    ring = _lonlat_box(500000, 5001300, 500500, 5001800)
    got = rs.nifc_mask(GRID, [{"type": "Polygon", "coordinates": [ring]}])
    assert got.dtype == bool and got.shape == GRID.shape
    assert got[:5, :5].all() and got.sum() == 25


def test_nifc_mask_repairs_invalid_geometry_and_accepts_features():
    # A bow-tie (self-intersecting) ring is invalid until make_valid splits it in two.
    ring = _lonlat_box(500000, 5001000, 500600, 5001800)
    bow = [ring[0], ring[2], ring[1], ring[3], ring[0]]
    feature = {
        "type": "Feature",
        "properties": {},
        "geometry": {"type": "Polygon", "coordinates": [bow]},
    }
    got = rs.nifc_mask(GRID, [feature])
    assert got.any() and not got.all()


def test_nifc_mask_survives_collapsed_pieces_from_server_side_generalising():
    # WFIGS generalised with maxAllowableOffset returns slivers whose points are all identical.
    # Beside a self-intersecting piece, make_valid raises "mixed-dimension" on such a sliver; the
    # perimeter must still count (the bow-tie's two lobes cover the lower-left 3 x 3 blocks).
    ring = _lonlat_box(500000, 5001000, 500600, 5001800)
    bow = [ring[0], ring[2], ring[1], ring[3], ring[0]]
    far = [ring[0][0] + 0.5, ring[0][1] + 0.5]  # well away from the bow-tie
    dot = [[far] * 4]
    multi = {"type": "MultiPolygon", "coordinates": [dot, [bow], dot]}
    got = rs.nifc_mask(GRID, [multi])
    assert got.any() and not got.all()


def test_nifc_mask_empty_and_missing_geometry():
    assert not rs.nifc_mask(GRID, []).any()
    assert not rs.nifc_mask(GRID, [None, {"type": "Feature", "geometry": None}]).any()


def test_nifc_mask_accepts_shapely_geometry():
    from shapely.geometry import Polygon

    got = rs.nifc_mask(GRID, [Polygon(_lonlat_box(500000, 5001700, 500200, 5001800))])
    assert got.sum() == 2 and got[0, :2].all()


# --- live: one test per source -------------------------------------------------------------------


@pytest.mark.live
def test_live_dist_hls_loss_finds_the_morton_clearcuts():
    from sarstellar.grid import grid_for_bbox

    grid = grid_for_bbox([-122.45, 46.55, -122.05, 46.80], 32610)
    loss = rs.dist_hls_loss(grid, date(2026, 5, 21), date(2026, 9, 30))
    assert loss.shape == grid.shape
    assert np.nanmax(loss) >= 0.5  # the spike found 106 reference blocks here
    assert (loss >= 0.5).sum() > 20


@pytest.mark.live
def test_live_dswx_water_sees_village_creek_flood():
    from sarstellar.grid import grid_for_bbox

    grid = grid_for_bbox([-94.45, 30.10, -94.00, 30.55], 32615)
    water = rs.dswx_water(grid, date(2026, 9, 13))
    assert water.shape == grid.shape
    assert np.isfinite(water).mean() > 0.3
    assert (water >= 0.5).sum() > 10  # creek and river corridor


@pytest.mark.live
def test_live_cdl_crop_marks_iowa_fields():
    from sarstellar.grid import grid_for_bbox

    grid = grid_for_bbox([-93.50, 42.10, -93.40, 42.19], 32615)
    crop = rs.cdl_crop(grid)
    assert crop.shape == grid.shape
    assert crop.mean() > 0.5  # central Iowa is corn and soybeans


@pytest.mark.live
def test_live_nifc_mask_from_wfigs_kaiser_canyon():
    import requests

    from sarstellar.grid import grid_for_bbox

    url = (
        "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
        "WFIGS_Interagency_Perimeters_YearToDate/FeatureServer/0/query"
    )
    params = {
        "where": "UPPER(poly_IncidentName) LIKE '%KAISER CANYON%'",
        "outSR": 4326,
        "f": "geojson",
    }
    feats = requests.get(url, params=params, timeout=120).json()["features"]
    assert feats, "WFIGS returned no Kaiser Canyon perimeter"  # the spike saw an invalid geometry
    bbox = [-119.3705, 48.0531, -118.7196, 48.3605]
    mask = rs.nifc_mask(grid_for_bbox(bbox, 32611), [f["geometry"] for f in feats])
    assert mask.mean() > 0.3

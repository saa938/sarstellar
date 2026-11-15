"""OPERA RTC-S1 burst mosaicking onto the NISAR block grid, including the 50% valid-area rule.

Offline tests build tiny GeoTIFFs and serve them through the fake fsspec session from
`test_read.py`. Two kinds of raster are used. The "other zone" ones (UTM 11 raster, UTM 10 grid)
check reprojection; the "aligned" ones (10 m pixels in the grid's own CRS) make every block hold
exactly 100 pixels, so valid fractions are exact numbers and can be asserted precisely.
The `live` test reads one real burst from ASF (needs ~/_netrc, run with `-m live`).
"""

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds

from sarstellar import read
from sarstellar.grid import grid_for_bbox
from sarstellar.read import https_fs, read_rtc_to_grid
from sarstellar.types import Grid
from test_read import KAISER_SMALL_BBOX, FakeFS

RTC = "https://fake.asf/RTC/OPERA_L2_RTC-S1_T115-000001-IW1_20260713T000000Z_S1A_30_v1.0"


def _write_tif(arr, transform, crs="EPSG:32611"):
    with rasterio.MemoryFile() as mem:
        with mem.open(driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1,
                      dtype=str(arr.dtype), crs=crs, transform=transform, tiled=True,
                      blockxsize=64, blockysize=64) as ds:
            ds.write(arr, 1)
        return mem.read()


def _burst(name, vv, vh=None, mask=None, transform=None, crs="EPSG:32611"):
    files = {f"{name}_VV.tif": _write_tif(vv.astype("float32"), transform, crs)}
    if vh is not None:
        files[f"{name}_VH.tif"] = _write_tif(vh.astype("float32"), transform, crs)
    zero = np.zeros(vv.shape, np.uint8) if mask is None else mask
    files[f"{name}_mask.tif"] = _write_tif(zero, transform, crs)
    return files


def _rtc_setup():
    """A zone-10 block grid across the zone 10/11 boundary, and a zone-11 raster that covers it."""
    grid = grid_for_bbox((-120.05, 46.95, -119.95, 47.05), 32610)
    left, bottom, right, top = transform_bounds(
        "EPSG:32610", "EPSG:32611", grid.xmin, grid.ymin, grid.xmax, grid.ymax
    )
    left, top = np.floor(left / 30) * 30 - 900, np.ceil(top / 30) * 30 + 900
    shape = (int((top - bottom) / 30) + 60, int((right - left) / 30) + 60)
    return grid, from_origin(left, top, 30.0, 30.0), shape


# --- reprojection and masks ---------------------------------------------------------------------


def test_read_rtc_to_grid_puts_other_zone_on_the_nisar_grid():
    grid, tr, shape = _rtc_setup()
    files = _burst(RTC, np.full(shape, 2.0), np.full(shape, 0.5), transform=tr)
    fs = FakeFS(files)
    out = read_rtc_to_grid([f"{RTC}_VV.tif", f"{RTC}_VH.tif"], grid, fs)
    assert set(out) == {"VV", "VH"}
    assert out["VV"].shape == out["VH"].shape == grid.shape
    assert np.allclose(out["VV"], 2.0) and np.allclose(out["VH"], 0.5)  # linear, same grid EPSG
    opened = [u for u, _ in fs.open_calls]
    assert opened.count(f"{RTC}_mask.tif") == 1  # one mask read serves both polarizations


def test_read_rtc_to_grid_drops_flagged_pixels_and_averages_overlap():
    grid, tr, shape = _rtc_setup()
    third = shape[0] // 3
    mask_a = np.zeros(shape, np.uint8)
    mask_a[:third] = 2  # burst A: layover over its top third
    vv_a = np.full(shape, 2.0)
    vv_a[2 * third :] = -1.0  # ... and non-positive values over its bottom third
    files = _burst(RTC + "A", vv_a, mask=mask_a, transform=tr)
    files |= _burst(RTC + "B", np.full(shape, 4.0), transform=tr)
    out = read_rtc_to_grid([f"{RTC}A_VV.tif", f"{RTC}B_VV.tif"], grid, FakeFS(files))["VV"]
    # Rows are checked well away from the band edges: the zone 11 raster is rotated a few degrees
    # relative to the zone 10 grid, so the edges tilt across the box.
    assert np.allclose(out[:25], 4.0)  # top: A flagged, only B counts
    assert np.allclose(out[47:73], 3.0)  # middle: both bursts, averaged in linear power
    assert np.allclose(out[-25:], 4.0)  # bottom: A non-positive, only B counts


def test_read_rtc_to_grid_missing_pol_and_uncovered_burst_are_nan():
    grid, tr, shape = _rtc_setup()
    far = from_origin(tr.c + 200000.0, tr.f, 30.0, 30.0)  # a burst 200 km east: no overlap
    files = _burst(RTC + "A", np.full(shape, 2.0), transform=tr)
    files |= _burst(RTC + "Z", np.full((50, 50), 9.0), transform=far)
    out = read_rtc_to_grid([f"{RTC}A_VV.tif", f"{RTC}Z_VV.tif"], grid, FakeFS(files))
    assert np.allclose(out["VV"], 2.0)  # the far burst contributes nothing
    assert np.isnan(out["VH"]).all() and out["VH"].shape == grid.shape


def test_read_rtc_to_grid_retries_flaky_server(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(read.time, "sleep", sleeps.append)
    grid, tr, shape = _rtc_setup()
    fs = FakeFS(_burst(RTC, np.full(shape, 2.0), transform=tr), fail_first=3)
    out = read_rtc_to_grid([f"{RTC}_VV.tif"], grid, fs)
    assert np.allclose(out["VV"], 2.0) and len(sleeps) == 3


# --- the 50% valid-area rule (same rule as NISAR blocks) ----------------------------------------

AGRID = Grid(epsg=32610, xmin=500000.0, xmax=500300.0, ymin=5200000.0, ymax=5200300.0)  # 3 x 3
A_TR = from_origin(AGRID.xmin, AGRID.ymax, 10.0, 10.0)  # 10 m pixels: exactly 10 x 10 per block


def _aligned(name, value, valid=None, cols=30):
    """A burst on AGRID's own 10 m lattice. `valid` is a bool array (True = usable pixel)."""
    full = np.full((30, cols), value)
    mask = np.zeros(full.shape, np.uint8)
    if valid is not None:
        mask[~valid[:, :cols]] = 2  # shadow/layover
    return _burst(name, full, mask=mask, transform=A_TR, crs="EPSG:32610")


def _read(files, *names):
    urls = [f"{n}_VV.tif" for n in names]
    return read_rtc_to_grid(urls, AGRID, FakeFS(files))["VV"]


def test_low_coverage_burst_is_not_averaged_from_a_few_pixels():
    valid = np.zeros((30, 30), bool)
    valid[::4, ::4] = True  # 9 to 16 usable pixels per 100-pixel block: well under half
    out = _read(_aligned(RTC, 5.0, valid), RTC)
    assert np.isnan(out).all()  # before the fix: finite everywhere, from a handful of pixels


def test_block_with_exactly_half_valid_pixels_is_kept_and_under_half_is_not():
    half = np.zeros((30, 30), bool)
    half[:, ::2] = True  # exactly 50 of 100 in every block
    assert np.allclose(_read(_aligned(RTC, 5.0, half), RTC), 5.0)
    forty = np.zeros((30, 30), bool)
    forty[:, np.arange(30) % 10 < 4] = True  # 40 of 100
    assert np.isnan(_read(_aligned(RTC, 5.0, forty), RTC)).all()


def test_burst_edge_block_needs_half_its_area_covered_by_the_burst():
    # the burst raster ends 40% (then 60%) of the way into the second block column
    narrow = _read(_aligned(RTC, 5.0, cols=14), RTC)
    assert np.allclose(narrow[:, 0], 5.0)
    assert np.isnan(narrow[:, 1:]).all()  # 40% covered: NaN, not the mean of a 4-pixel sliver
    wider = _read(_aligned(RTC, 5.0, cols=16), RTC)
    assert np.allclose(wider[:, :2], 5.0)  # 60% covered: kept, mean of the covered pixels
    assert np.isnan(wider[:, 2]).all()


def test_overlapping_bursts_are_weighted_by_valid_area():
    partial = np.zeros((30, 30), bool)
    partial[:, np.arange(30) % 10 < 6] = True  # burst B is usable on 60% of every block
    files = _aligned(RTC + "A", 2.0) | _aligned(RTC + "B", 4.0, partial)
    out = _read(files, RTC + "A", RTC + "B")
    # 100 pixels of 2.0 pooled with 60 pixels of 4.0; an equal-weight average would give 3.0
    assert np.allclose(out, (100 * 2.0 + 60 * 4.0) / 160)


def test_overlapping_burst_below_half_coverage_does_not_pull_the_mosaic():
    sliver = np.zeros((30, 30), bool)
    sliver[:, np.arange(30) % 10 < 3] = True  # burst B is usable on 30% of every block
    files = _aligned(RTC + "A", 2.0) | _aligned(RTC + "B", 4.0, sliver)
    assert np.allclose(_read(files, RTC + "A", RTC + "B"), 2.0)  # A alone, not 2.0 / 4.0 mixed


def test_other_zone_raster_that_fully_covers_the_grid_stays_fully_valid():
    grid, tr, shape = _rtc_setup()  # rotated raster with margin: no block loses its half
    fs = FakeFS(_burst(RTC, np.full(shape, 2.0), transform=tr))
    out = read_rtc_to_grid([f"{RTC}_VV.tif"], grid, fs)
    assert np.isfinite(out["VV"]).all()


# --- live ----------------------------------------------------------------------------------------

RTC_BURST = (  # the one Sentinel-1 burst over KAISER_SMALL_BBOX on 2026-07-13 (T115, zone 11)
    "https://cumulus.asf.earthdatacloud.nasa.gov/OPERA/OPERA_L2_RTC-S1/"
    "OPERA_L2_RTC-S1_T115-245651-IW1_20260713T141241Z_20261010T060238Z_S1D_30_v1.0/"
    "OPERA_L2_RTC-S1_T115-245651-IW1_20260713T141241Z_20261010T060238Z_S1D_30_v1.0"
)


@pytest.mark.live
def test_live_rtc_burst_lands_on_the_nisar_grid():
    grid = grid_for_bbox(KAISER_SMALL_BBOX, 32610)  # NISAR's zone 10 grid, not the burst's zone 11
    out = read_rtc_to_grid([f"{RTC_BURST}_VV.tif", f"{RTC_BURST}_VH.tif"], grid, https_fs())
    assert out["VV"].shape == out["VH"].shape == grid.shape
    assert np.isfinite(out["VV"]).mean() > 0.9 and np.isfinite(out["VH"]).mean() > 0.9
    assert -20 < 10 * np.log10(np.nanmedian(out["VV"])) < -5
    assert -30 < 10 * np.log10(np.nanmedian(out["VH"])) < -10

"""Independent reference answers to score radar change flags against.

Radar change flags are only worth reporting if something other than radar agrees. These four
functions turn four independent sources into the same shape: one value per 1-ha block of the
analysis grid.

* `dist_hls_loss`  OPERA DIST-ALERT-HLS: where optical imagery shows a big vegetation loss (a
                   clearcut, a burn scar, a harvest).
* `dswx_water`     OPERA DSWx-S1 / DSWx-HLS: where surface water is mapped on a given day.
* `cdl_crop`       USDA Cropland Data Layer: which blocks are cultivated cropland.
* `nifc_mask`      NIFC/WFIGS fire perimeters: which blocks lie inside a mapped fire.

The pure array logic (`dist_loss_indicator`, `water_indicator`, `cdl_cultivated_indicator`, the
`*_to_grid` helpers) is separate from the network code so it can be tested on tiny synthetic
rasters. Reprojection onto the grid is `sarstellar.grid.to_grid_with_coverage`, so a block only
gets a value when at least half of its area holds valid reference pixels.
"""

from __future__ import annotations

import logging
import re
import time
from contextlib import ExitStack
from datetime import UTC, date, datetime, timedelta
from typing import Any

import numpy as np
import requests

from .grid import to_grid_with_coverage
from .read import _open_tif, _rtc_window, https_fs
from .search import _box_param, _cmr_items, _temporal_param
from .types import Grid

log = logging.getLogger(__name__)

DIST_COLLECTION = "OPERA_L3_DIST-ALERT-HLS_V1"
DSWX_S1_COLLECTION = "OPERA_L3_DSWX-S1_V1"
DSWX_HLS_COLLECTION = "OPERA_L3_DSWX-HLS_V1"

MIN_VALID_FRAC = 0.5  # a block needs half its area covered by valid reference pixels
COG_RETRIES = 6

# --- OPERA DIST-ALERT-HLS ------------------------------------------------------------------------

DIST_EPOCH = date(2020, 12, 31)  # VEG-DIST-DATE counts days from here
# VEG-DIST-STATUS: 0 none, 1 and 4 first detections (not yet confirmed: skipped), 2/3/5/6/7/8
# provisional or confirmed, ongoing or finished. 255 is no data. (Same rule as the clearcut spike.)
DIST_LOSS_STATUSES = (2, 3, 5, 6, 7, 8)
DIST_MIN_LOSS_PCT = 50  # VEG-ANOM-MAX is the peak vegetation loss in percent
_DIST_LAYERS = {"status": "VEG-DIST-STATUS", "date": "VEG-DIST-DATE", "anom": "VEG-ANOM-MAX"}
_DIST_UR = re.compile(r"^OPERA_L3_DIST-ALERT-HLS_(?P<tile>T\d{2}[A-Z]{3})_(?P<acq>\d{8})T\d{6}Z_")


def dist_loss_indicator(status, date_days, anom_max, start: date, end: date) -> np.ndarray:
    """1.0 where a pixel lost >= 50% vegetation with a disturbance date in [start, end], else 0.0.

    NaN where `status` is 255 (no data). `date_days` is VEG-DIST-DATE (days since 2020-12-31).
    """
    status, when, anom = (np.asarray(a) for a in (status, date_days, anom_max))
    d0, d1 = (start - DIST_EPOCH).days, (end - DIST_EPOCH).days
    loss = (
        np.isin(status, DIST_LOSS_STATUSES)
        & (anom >= DIST_MIN_LOSS_PCT)
        & (anom <= 100)
        & (when >= d0)
        & (when <= d1)
    )
    out = loss.astype("float64")
    out[status == 255] = np.nan
    return out


def dist_layers_to_grid(
    status, date_days, anom_max, transform, crs, grid: Grid, start: date, end: date
) -> np.ndarray:
    """Per-block fraction of pixels with in-window vegetation loss (NaN: under half valid)."""
    indicator = dist_loss_indicator(status, date_days, anom_max, start, end)
    return to_grid_with_coverage(indicator, transform, crs, grid, MIN_VALID_FRAC)[0]


def _umm_urls(item: dict[str, Any]) -> list[str]:
    umm = item["umm"]
    return [
        link["URL"]
        for link in umm.get("RelatedUrls", [])
        if link.get("Type") == "GET DATA" and link.get("URL", "").startswith("https://")
    ]


def pick_dist_granules(items: list[dict], end: date, lag_days: int = 30) -> list[dict]:
    """For each HLS tile, the latest DIST-ALERT granule acquired from `end` to `end + lag_days`.

    DIST-ALERT keeps a running record per tile, so a granule acquired shortly after the window
    already holds every disturbance dated inside it; the latest one has had the most looks
    through clouds. Returns [{"tile", "acquired", "ur", "urls": {status, date, anom}}].
    """
    latest: dict[str, dict] = {}
    for item in items:
        ur = item["umm"].get("GranuleUR", "")
        m = _DIST_UR.match(ur)
        if m is None:
            continue
        acquired = datetime.strptime(m["acq"], "%Y%m%d").date()
        if not (end <= acquired <= end + timedelta(days=lag_days)):
            continue
        urls = {}
        for key, layer in _DIST_LAYERS.items():
            hit = [u for u in _umm_urls(item) if u.endswith(f"_{layer}.tif")]
            if hit:
                urls[key] = hit[0]
        if len(urls) != len(_DIST_LAYERS):
            continue
        cur = latest.get(m["tile"])
        if cur is None or acquired > cur["acquired"]:
            latest[m["tile"]] = {"tile": m["tile"], "acquired": acquired, "ur": ur, "urls": urls}
    return [latest[t] for t in sorted(latest)]


def dist_hls_loss(grid: Grid, start: date, end: date, fs=None, lag_days: int = 30) -> np.ndarray:
    """Per 1-ha block: fraction of pixels with >= 50% OPERA DIST-ALERT-HLS vegetation loss dated
    inside [start, end]. NaN where under half the block has valid data. Shape `grid.shape`."""
    fs = fs or https_fs()
    items = _cmr_umm(DIST_COLLECTION, _grid_bbox(grid), end, end + timedelta(days=lag_days))
    out = np.full(grid.shape, np.nan)
    for g in pick_dist_granules(items, end, lag_days):
        arrays, transform, crs = _read_layers(g["urls"], grid, fs)
        if arrays is None:
            continue
        tile = dist_layers_to_grid(
            arrays["status"], arrays["date"], arrays["anom"], transform, crs, grid, start, end
        )
        out = _fill(out, tile)
    return out


# --- OPERA DSWx ----------------------------------------------------------------------------------

# B01_WTR: 0 not water, 1 open water, 2 partial surface water, 3 inundated vegetation (DSWx-S1
# only). 252 snow/ice, 253 cloud/shadow or layover/shadow, 254 ocean mask, 255 fill: all no data.
WATER_CLASSES = (1, 2, 3)
_DSWX_UR = re.compile(
    r"^OPERA_L3_DSWx-(?P<product>HLS|S1)_(?P<tile>T\d{2}[A-Z]{3})_(?P<acq>\d{8})T(?P<hms>\d{6})Z_"
)
MAX_DSWX_GRANULES = 6


def water_indicator(wtr, classes=WATER_CLASSES) -> np.ndarray:
    """1.0 for water classes, 0.0 for land, NaN for masked codes (>= 250)."""
    wtr = np.asarray(wtr)
    out = np.isin(wtr, classes).astype("float64")
    out[wtr >= 250] = np.nan
    return out


def water_layers_to_grid(wtr, transform, crs, grid: Grid, classes=WATER_CLASSES) -> np.ndarray:
    """Per-block water fraction among valid pixels (NaN: under half the block is valid)."""
    return to_grid_with_coverage(
        water_indicator(wtr, classes), transform, crs, grid, MIN_VALID_FRAC
    )[0]


def pick_dswx_granules(items: list[dict], when: date, max_days: int = 3) -> list[dict]:
    """DSWx granules acquired within `max_days` of `when`, nearest first.

    Returns [{"tile", "acquired", "ur", "url"}] with `url` the B01_WTR.tif water map.
    """
    picked = []
    for item in items:
        ur = item["umm"].get("GranuleUR", "")
        m = _DSWX_UR.match(ur)
        if m is None:
            continue
        acquired = datetime.strptime(m["acq"], "%Y%m%d").date()
        if abs((acquired - when).days) > max_days:
            continue
        wtr = [u for u in _umm_urls(item) if u.endswith("_B01_WTR.tif")]
        if wtr:
            picked.append({"tile": m["tile"], "acquired": acquired, "ur": ur, "url": wtr[0]})
    picked.sort(key=lambda p: (abs((p["acquired"] - when).days), p["acquired"], p["tile"], p["ur"]))
    return picked


def _dswx_product_water(product: str, grid: Grid, when: date, max_days: int, fs) -> np.ndarray:
    collection = DSWX_S1_COLLECTION if product == "S1" else DSWX_HLS_COLLECTION
    span = timedelta(days=max_days)
    items = _cmr_umm(collection, _grid_bbox(grid), when - span, when + span)
    out = np.full(grid.shape, np.nan)
    for g in pick_dswx_granules(items, when, max_days)[:MAX_DSWX_GRANULES]:
        arrays, transform, crs = _read_layers({"wtr": g["url"]}, grid, fs)
        if arrays is not None:
            out = _fill(out, water_layers_to_grid(arrays["wtr"], transform, crs, grid))
    return out


def dswx_water(grid: Grid, when: date | datetime, fs=None, max_days: int = 3) -> np.ndarray:
    """Per 1-ha block water fraction on the DSWx map nearest `when` (within +-`max_days`).

    DSWx-S1 comes first because radar sees through cloud; DSWx-HLS fills blocks it has no data
    for (HLS is optical and often clouded out in a storm). Water means open water, partial
    surface water or, for DSWx-S1, inundated vegetation. NaN where neither product has data.
    """
    when = when.date() if isinstance(when, datetime) else when
    fs = fs or https_fs()
    out = _dswx_product_water("S1", grid, when, max_days, fs)
    if np.isnan(out).any():
        out = _fill(out, _dswx_product_water("HLS", grid, when, max_days, fs))
    return out


# --- USDA Cropland Data Layer --------------------------------------------------------------------

CROPSCAPE_URL = "https://nassgeodata.gmu.edu/CropScapeService/wms_cdlall.cgi"
CDL_MAX_YEARS_BACK = 6
# Cultivated cropland: row crops and small grains (1-60), fallow/idle (61), orchards and tree
# crops (66-77), and specialty and double-crop codes (204-254).
CDL_CULTIVATED = frozenset([*range(1, 62), *range(66, 78), *range(204, 255)])
CDL_FOREST = frozenset({63, 141, 142, 143})
CDL_DEVELOPED = frozenset({121, 122, 123, 124})


def cdl_cultivated_indicator(cdl) -> np.ndarray:
    """1.0 for cultivated classes, 0.0 for everything else, NaN for background (0) and 81."""
    return cdl_class_indicator(cdl, CDL_CULTIVATED)


def cdl_class_indicator(cdl, classes) -> np.ndarray:
    """1.0 where the CDL code is in `classes`, 0.0 elsewhere, NaN for 0 (background) and 81."""
    cdl = np.asarray(cdl)
    out = np.isin(cdl, list(classes)).astype("float64")
    out[(cdl == 0) | (cdl == 81)] = np.nan
    return out


def cdl_years_to_try(year: int | None, today: date | None = None) -> list[int]:
    """The CDL year asked for, or this year and earlier years, newest first."""
    if year is not None:
        return [year]
    this_year = (today or date.today()).year
    return list(range(this_year, this_year - CDL_MAX_YEARS_BACK, -1))


def _wcs_get_coverage(coverage: str, bounds: tuple[float, float, float, float], res: float):
    """One CropScape WCS request in EPSG:5070. Returns (array, transform, crs), or None when the
    service has no such coverage (a year not published yet)."""
    from rasterio.io import MemoryFile

    params = {
        "service": "WCS", "version": "1.0.0", "request": "GetCoverage", "coverage": coverage,
        "crs": "EPSG:5070", "bbox": ",".join(f"{v:.0f}" for v in bounds),
        "resx": res, "resy": res, "format": "image/tiff",
    }  # fmt: skip
    for attempt in range(1, 4):
        try:
            resp = requests.get(CROPSCAPE_URL, params=params, timeout=120)
            break
        except (requests.ConnectionError, requests.Timeout):
            if attempt == 3:
                raise
            time.sleep(2**attempt)
    if "xml" in resp.headers.get("content-type", ""):
        if 'locator="coverage"' in resp.text or "Invalid coverage" in resp.text:
            return None
        raise RuntimeError(f"CropScape WCS error: {resp.text[:300]}")
    with MemoryFile(resp.content) as mem, mem.open() as ds:
        return ds.read(1), ds.transform, ds.crs.to_string()


def fetch_cdl(grid: Grid, year: int | None = None):
    """The CDL class raster over `grid` at 30 m: (array, transform, crs, year used)."""
    from rasterio.crs import CRS
    from rasterio.warp import transform_bounds

    bounds = transform_bounds(
        CRS.from_epsg(grid.epsg), CRS.from_epsg(5070),
        grid.xmin, grid.ymin, grid.xmax, grid.ymax, densify_pts=21,
    )  # fmt: skip
    pad = 90.0
    bounds = (bounds[0] - pad, bounds[1] - pad, bounds[2] + pad, bounds[3] + pad)
    for y in cdl_years_to_try(year):
        got = _wcs_get_coverage(f"cdl_{y}", bounds, 30)
        if got is not None:
            return (*got, y)
    raise LookupError(f"no Cropland Data Layer available for {year or 'any recent year'}")


def cdl_fraction(grid: Grid, classes, year: int | None = None) -> np.ndarray:
    """Per-block fraction of the CDL pixels whose class is in `classes` (NaN: under half valid)."""
    arr, transform, crs, _year = fetch_cdl(grid, year)
    ind = cdl_class_indicator(arr, classes)
    return to_grid_with_coverage(ind, transform, crs, grid, MIN_VALID_FRAC)[0]


def cdl_crop(grid: Grid, year: int | None = None) -> np.ndarray:
    """Bool per block: at least half the block is cultivated cropland in the latest CDL year."""
    arr, transform, crs, _year = fetch_cdl(grid, year)
    frac = to_grid_with_coverage(
        cdl_cultivated_indicator(arr), transform, crs, grid, MIN_VALID_FRAC
    )[0]
    return np.nan_to_num(frac, nan=0.0) >= 0.5


# --- NIFC / WFIGS fire perimeters ----------------------------------------------------------------

WFIGS_URL = (
    "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
    "WFIGS_Interagency_Perimeters_YearToDate/FeatureServer/0/query"
)
_WFIGS_FIELDS = (
    "poly_IncidentName,poly_GISAcres,attr_FireDiscoveryDateTime,attr_ContainmentDateTime,"
    "attr_FireOutDateTime,poly_PolygonDateTime,attr_POOState,attr_IncidentTypeCategory,"
    "attr_UniqueFireIdentifier"
)


def _as_polygonal(geom):
    """A valid Polygon/MultiPolygon from a geometry, repairing it first if needed."""
    import shapely
    from shapely.validation import make_valid

    if geom is None or geom.is_empty:
        return None
    if not geom.is_valid:
        geom = make_valid(geom)
    if geom.geom_type == "GeometryCollection":  # make_valid can return polygons plus slivers
        parts = [g for g in shapely.get_parts(geom) if g.geom_type in ("Polygon", "MultiPolygon")]
        geom = shapely.union_all(parts) if parts else None
    return geom if geom is not None and not geom.is_empty else None


def _to_shapely(p):
    from shapely.geometry import shape
    from shapely.geometry.base import BaseGeometry

    if p is None:
        return None
    if isinstance(p, BaseGeometry):
        return p
    if isinstance(p, dict):
        geom = p.get("geometry") if p.get("type") == "Feature" else p
        return shape(geom) if geom else None
    raise TypeError(f"cannot read a perimeter from {type(p).__name__}")


def block_centres_lonlat(grid: Grid) -> tuple[np.ndarray, np.ndarray]:
    """(lon, lat) of every block centre, each shaped `grid.shape`."""
    from pyproj import Transformer

    ny, nx = grid.shape
    xs = grid.xmin + grid.res * (np.arange(nx) + 0.5)
    ys = grid.ymax - grid.res * (np.arange(ny) + 0.5)
    xx, yy = np.meshgrid(xs, ys)
    lon, lat = Transformer.from_crs(grid.epsg, 4326, always_xy=True).transform(xx, yy)
    return np.asarray(lon), np.asarray(lat)


def nifc_mask(grid: Grid, perimeters) -> np.ndarray:
    """Bool per block: the block centre lies inside any perimeter.

    `perimeters` are lon/lat shapely geometries, GeoJSON geometries or GeoJSON features. Invalid
    rings (WFIGS has many self-intersecting ones) are repaired with `make_valid` first.
    """
    import shapely

    mask = np.zeros(grid.shape, dtype=bool)
    lon = lat = None
    for p in perimeters:
        geom = _as_polygonal(_to_shapely(p))
        if geom is None:
            continue
        if lon is None:
            lon, lat = block_centres_lonlat(grid)
        mask |= shapely.contains_xy(geom, lon, lat)
    return mask


def _ms_to_date(ms) -> date | None:
    return datetime.fromtimestamp(ms / 1000, UTC).date() if ms else None


def wfigs_perimeters(
    bbox=None,
    start: date | None = None,
    end: date | None = None,
    min_acres: float = 1000,
    generalize_deg: float | None = None,
) -> list[dict[str, Any]]:
    """2026 NIFC/WFIGS fire perimeters, one dict per perimeter, optionally filtered.

    Keeps perimeters of at least `min_acres` that touch `bbox` (west, south, east, north) and were
    discovered from `start` to `end`. Each dict has name, acres, discovered, contained, out
    (dates or None), state ("WA"), kind ("WF" wildfire, "RX" prescribed), fire_id and `geometry`
    (GeoJSON, possibly invalid: `nifc_mask` repairs it). `generalize_deg` simplifies geometry.
    """
    where = [f"poly_GISAcres >= {float(min_acres)}"]
    if start:
        where.append(f"attr_FireDiscoveryDateTime >= timestamp '{start:%Y-%m-%d} 00:00:00'")
    if end:
        where.append(f"attr_FireDiscoveryDateTime <= timestamp '{end:%Y-%m-%d} 23:59:59'")
    params: dict[str, Any] = {
        "where": " AND ".join(where), "outFields": _WFIGS_FIELDS, "outSR": 4326, "f": "geojson",
        "returnGeometry": "true", "resultRecordCount": 100,
    }  # fmt: skip
    if bbox is not None:
        w, s, e, n = (float(v) for v in bbox)
        params.update(
            geometry=f"{w},{s},{e},{n}", geometryType="esriGeometryEnvelope", inSR=4326,
            spatialRel="esriSpatialRelIntersects",
        )  # fmt: skip
    if generalize_deg:
        params["maxAllowableOffset"] = generalize_deg
    out: list[dict[str, Any]] = []
    offset = 0
    while True:
        params["resultOffset"] = offset
        resp = _get_json(WFIGS_URL, params)
        feats = resp.get("features", [])
        for f in feats:
            a = f["properties"]
            out.append(
                {
                    "name": a.get("poly_IncidentName"),
                    "acres": a.get("poly_GISAcres"),
                    "discovered": _ms_to_date(a.get("attr_FireDiscoveryDateTime")),
                    "contained": _ms_to_date(a.get("attr_ContainmentDateTime")),
                    "out": _ms_to_date(a.get("attr_FireOutDateTime")),
                    "state": (a.get("attr_POOState") or "").removeprefix("US-") or None,
                    "kind": a.get("attr_IncidentTypeCategory"),
                    "fire_id": a.get("attr_UniqueFireIdentifier"),
                    "geometry": f.get("geometry"),
                }
            )
        offset += len(feats)
        if not feats or not (
            resp.get("exceededTransferLimit")
            or resp.get("properties", {}).get("exceededTransferLimit")
        ):
            return out


def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    for attempt in range(1, 5):
        try:
            resp = requests.get(url, params=params, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(str(data["error"])[:200])
            return data
        except (requests.RequestException, RuntimeError, ValueError):
            if attempt == 4:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


# --- shared plumbing -----------------------------------------------------------------------------


def _grid_bbox(grid: Grid) -> tuple[float, float, float, float]:
    """The grid's footprint as a lon/lat box (west, south, east, north)."""
    from rasterio.crs import CRS
    from rasterio.warp import transform_bounds

    return transform_bounds(
        CRS.from_epsg(grid.epsg), CRS.from_epsg(4326),
        grid.xmin, grid.ymin, grid.xmax, grid.ymax, densify_pts=21,
    )  # fmt: skip


def _cmr_umm(short_name: str, bbox, start: date, end: date) -> list[dict]:
    return _cmr_items(
        [
            ("short_name", short_name),
            ("bounding_box", _box_param(bbox)),
            ("temporal", _temporal_param(start, end)),
            ("page_size", "2000"),
        ]
    )


def _fill(base: np.ndarray, extra: np.ndarray) -> np.ndarray:
    """`base` with its NaN cells taken from `extra` (nearest or best source goes in `base`)."""
    return np.where(np.isfinite(base), base, extra)


def _read_layers(urls: dict[str, str], grid: Grid, fs):
    """Read same-raster COG layers over the grid. Returns ({name: array}, transform, crs), or
    (None, None, None) when the raster does not reach the grid."""
    with ExitStack() as stack:
        datasets = {k: _open_tif(u, fs, COG_RETRIES, stack) for k, u in urls.items()}
        first = next(iter(datasets.values()))
        win = _rtc_window(first, grid)
        if win is None:
            return None, None, None
        arrays = {k: ds.read(1, window=win) for k, ds in datasets.items()}
        return arrays, first.window_transform(win), first.crs

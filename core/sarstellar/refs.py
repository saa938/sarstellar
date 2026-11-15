"""Reference layers that sit beside the radar data.

`nlcd(grid)` returns the land-cover group of every 1-ha block. It is the stratum the detector
estimates its equivalent number of looks (ENL) for (Ruling R13): forest, grass and crops do not
share one noise level, so one scene-wide ENL over-alarms in the noisy cover.

The other lookups decorate a result: `svi_tracts` (who lives there), `nifc_perimeters` and
`firms_count` (fire evidence for the cause rules) and `weather` (freeze and rain). All of them
fail quietly, because a missing reference lowers confidence but never breaks a run.
"""

from __future__ import annotations

import csv
import logging
import os
from datetime import UTC, date, datetime, timedelta

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


# --- people, fire and weather -------------------------------------------------------------------
# Each lookup takes two tries and then gives up quietly (see the module docstring).

SVI_URL = (
    "https://onemap.cdc.gov/onemapservices/rest/services/SVI/"
    "CDC_ATSDR_Social_Vulnerability_Index_2022_USA/FeatureServer/2/query"
)
WFIGS_URL = (
    "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
    "WFIGS_Interagency_Perimeters_YearToDate/FeatureServer/0/query"
)
FIRMS_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{source}/{area}/{days}/{day}"
FIRMS_SOURCES = ("VIIRS_SNPP_SP", "VIIRS_SNPP_NRT")  # archive, then near-real-time
FIRMS_MAX_DAYS = 10  # the area API's longest day range
OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
REF_TIMEOUT_S = 30
REF_TRIES = 2
SVI_PAGE = 2000
SVI_MISSING = -999  # the CDC's code for a tract with no ranking


def _ref_get(url: str, params: dict | None = None):
    """GET with two tries (1 s apart) and a 30 s timeout; raises OSError after the second."""

    def get():
        r = requests.get(url, params=params, timeout=REF_TIMEOUT_S)
        r.raise_for_status()
        return r

    return read.with_retries(get, REF_TRIES)()


def _envelope(bbox) -> dict:
    return {
        "geometry": ",".join(str(float(v)) for v in bbox),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "where": "1=1",
        "f": "geojson",
    }


def svi_tracts(bbox) -> list[dict]:
    """CDC Social Vulnerability Index 2022 tracts that touch `bbox` (west, south, east, north).

    Returns [{"geoid", "rpl_themes", "name", "geometry"}] with `rpl_themes` the overall 0..1
    percentile rank (higher is more vulnerable) and `geometry` a GeoJSON polygon in lon/lat.
    Tracts with no ranking (-999) are dropped. Any error gives [].
    """
    params = {
        **_envelope(bbox), "outFields": "FIPS,LOCATION,RPL_THEMES", "returnGeometry": "true",
        "geometryPrecision": "5", "resultRecordCount": str(SVI_PAGE),
    }
    out: list[dict] = []
    try:
        for page in range(10):  # 2000 tracts a page; a 20 km box has a few dozen
            params["resultOffset"] = str(page * SVI_PAGE)
            data = _ref_get(SVI_URL, params).json()
            feats = data.get("features") or []
            for f in feats:
                p = f.get("properties") or {}
                rank = p.get("RPL_THEMES")
                if rank is None or float(rank) < 0 or not f.get("geometry"):
                    continue  # -999 (no ranking) and anything else negative
                out.append({"geoid": str(p["FIPS"]), "rpl_themes": float(rank),
                            "name": str(p.get("LOCATION") or ""), "geometry": f["geometry"]})
            if not (data.get("exceededTransferLimit") and feats):
                break
    except Exception as exc:  # noqa: BLE001 - optional context
        log.warning("SVI unavailable: %s: %s", type(exc).__name__, exc)
        return []
    return out


def nifc_perimeters(bbox, year: int = 2026) -> list[dict]:
    """NIFC WFIGS year-to-date fire perimeters touching `bbox`, discovered in `year`.

    Returns [{"name", "acres", "geometry"}] (GeoJSON in lon/lat, simplified to about 10 m). The
    layer only holds the current year, so any other year gives []. Any error also gives [].
    """
    params = {
        **_envelope(bbox), "returnGeometry": "true", "geometryPrecision": "5",
        "maxAllowableOffset": "0.0001",
        "outFields": "poly_IncidentName,attr_IncidentName,poly_GISAcres,attr_FireDiscoveryDateTime",
    }
    try:
        feats = _ref_get(WFIGS_URL, params).json().get("features") or []
    except Exception as exc:  # noqa: BLE001 - optional context
        log.warning("NIFC perimeters unavailable: %s: %s", type(exc).__name__, exc)
        return []
    out = []
    for f in feats:
        p = f.get("properties") or {}
        found = p.get("attr_FireDiscoveryDateTime")  # epoch milliseconds, UTC
        if found is not None and datetime.fromtimestamp(found / 1000, UTC).year != int(year):
            continue
        if not f.get("geometry"):
            continue
        out.append({"name": p.get("poly_IncidentName") or p.get("attr_IncidentName") or "",
                    "acres": p.get("poly_GISAcres"), "geometry": f["geometry"]})
    return out


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def firms_count(geometry, start, end) -> int | None:
    """NASA FIRMS VIIRS detections inside a GeoJSON `geometry` from `start` to `end` (inclusive).

    Needs a FIRMS map key in the environment variable `FIRMS_MAP_KEY` (free from NASA, never in
    the repo). Returns None, which the rules read as "no detections", when there is no key or the
    lookup fails. The archive (SP) and near-real-time feeds overlap, so rows are de-duplicated.
    """
    key = os.environ.get("FIRMS_MAP_KEY")
    if not key:
        return None
    from shapely import contains_xy
    from shapely.geometry import shape

    poly = shape(geometry)
    w, s, e, n = poly.bounds
    area = f"{w:.5f},{s:.5f},{e:.5f},{n:.5f}"
    first, last = _as_date(start), _as_date(end)
    rows: set[tuple] = set()
    try:
        for source in FIRMS_SOURCES:
            day = first
            while day <= last:
                days = min(FIRMS_MAX_DAYS, (last - day).days + 1)
                url = FIRMS_URL.format(key=key, source=source, area=area, days=days,
                                       day=day.isoformat())
                lines = _ref_get(url).text.strip().splitlines()
                reader = csv.DictReader(lines)
                if not {"latitude", "longitude"} <= set(reader.fieldnames or ()):
                    raise ValueError("unexpected FIRMS reply")  # e.g. an invalid-key message
                for r in reader:
                    rows.add((r["latitude"], r["longitude"], r.get("acq_date"), r.get("acq_time")))
                day += timedelta(days=days)
    except Exception as exc:  # noqa: BLE001 - optional context; the URL holds the key: not logged
        log.warning("FIRMS unavailable: %s", type(exc).__name__)
        return None
    return int(sum(contains_xy(poly, float(lon), float(lat)) for lat, lon, _, _ in rows))


def weather(lon: float, lat: float, when) -> dict:
    """Open-Meteo archive values for one day: {"min_temp_c", "rain_mm"}; None on any error."""
    none = {"min_temp_c": None, "rain_mm": None}
    try:
        day = _as_date(when).isoformat()
        params = {"latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}", "start_date": day,
                  "end_date": day, "daily": "temperature_2m_min,precipitation_sum",
                  "timezone": "UTC"}
        daily = _ref_get(OPEN_METEO_URL, params).json()["daily"]
        t, rain = daily["temperature_2m_min"][0], daily["precipitation_sum"][0]
    except Exception as exc:  # noqa: BLE001 - optional context
        log.warning("weather unavailable: %s: %s", type(exc).__name__, exc)
        return none
    return {"min_temp_c": None if t is None else float(t),
            "rain_mm": None if rain is None else float(rain)}

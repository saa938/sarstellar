"""Where to look for sites: region tables, box geometry, and per-kind candidate generators.

`modal_app/sites.py` turns these candidates into verified sites (pair search, reference check).
Everything here only proposes 10 km boxes: forest loss from DIST-ALERT-HLS scans, fire boxes from
NIFC perimeters, flood boxes from DSWx water gain, and crop and stable boxes from the CDL.
"""

from __future__ import annotations

import logging
import math
import time
from datetime import UTC, date, datetime, timedelta
from typing import Any

import numpy as np
import requests

from sarstellar import refs_scoring as refs
from sarstellar.grid import grid_for_bbox

log = logging.getLogger("sites")

BOX_KM = 10.0
MAX_OVERLAP = 0.25
SCAN = (date(2026, 5, 15), date(2026, 10, 31))  # window for the region-wide disturbance scan

# Region tables: name -> (west, south, east, north). Rough rectangles, only used to look in.
FOREST = {
    "WA-west": (-123.6, 46.2, -121.7, 48.3), "OR-west": (-124.0, 42.9, -122.0, 45.6),
    "CA-north": (-124.0, 39.9, -122.0, 41.9), "ID-north": (-116.9, 46.4, -115.0, 48.6),
    "MT-nw": (-115.6, 47.6, -113.6, 48.9), "GA-south": (-84.5, 31.0, -81.8, 33.0),
    "AL-MS": (-88.8, 31.0, -86.2, 33.2), "LA-TX": (-94.4, 30.3, -92.0, 32.7),
    "AR": (-93.8, 33.2, -91.6, 35.0), "SC-NC": (-80.6, 33.2, -78.0, 35.6),
    "VA": (-79.0, 36.9, -76.8, 38.0), "ME": (-70.0, 44.8, -67.8, 46.9),
    "MN": (-95.0, 46.8, -92.0, 48.2), "WI-MI": (-90.0, 45.4, -87.0, 46.8),
    "WV-KY": (-82.2, 37.2, -80.2, 38.8), "NY-PA": (-78.6, 41.3, -76.6, 42.6),
}  # fmt: skip
CROPS = {
    "CA-central-valley": (-121.4, 36.0, -119.4, 38.2), "WA-columbia-basin": (-119.9, 46.2, -118.7, 47.3),
    "ID-snake": (-114.3, 42.5, -113.0, 43.4), "IA": (-95.0, 41.6, -92.0, 43.0),
    "IL": (-90.0, 39.9, -88.0, 41.3), "IN": (-86.8, 40.0, -85.2, 41.0), "NE": (-98.3, 40.6, -96.6, 41.8),
    "KS": (-100.0, 37.6, -98.0, 38.8), "MN": (-96.3, 44.0, -94.5, 45.0), "ND": (-97.8, 46.8, -96.8, 48.2),
    "AR-delta": (-91.4, 34.6, -90.5, 35.9), "MS-delta": (-91.0, 33.0, -90.3, 34.2),
    "TX-plains": (-102.0, 33.6, -100.8, 34.8),
}  # fmt: skip
STABLE = {  # name -> (rect, class set, minimum share of the box)
    "forest": {
        "WV": (-80.8, 38.2, -79.6, 38.9), "NY-adirondack": (-74.8, 43.6, -73.8, 44.4),
        "ME-north": (-69.5, 45.5, -68.0, 46.5), "MO-AR-ozarks": (-92.5, 36.3, -91.0, 37.3),
        "TN-NC-smokies": (-84.0, 35.4, -83.0, 36.0), "VA-blue-ridge": (-79.8, 37.4, -78.7, 38.3),
        "PA-wilds": (-78.6, 41.2, -77.0, 41.9), "MI-up": (-89.0, 46.0, -87.5, 46.8),
        "WA-cascades": (-121.6, 47.8, -121.0, 48.6), "WI-north": (-91.0, 45.6, -89.6, 46.5),
    },
    "urban": {
        "NY": (-74.2, 40.55, -73.75, 40.9), "IL": (-88.0, 41.6, -87.5, 42.1), "CA-la": (-118.6, 33.8, -117.8, 34.2),
        "TX-houston": (-95.7, 29.5, -95.1, 30.0), "TX-dallas": (-97.1, 32.6, -96.5, 33.0),
        "AZ": (-112.3, 33.3, -111.8, 33.7), "PA": (-75.3, 39.9, -75.0, 40.1), "GA": (-84.6, 33.6, -84.2, 33.9),
        "FL": (-80.4, 25.6, -80.1, 26.1), "MA": (-71.2, 42.25, -70.95, 42.45), "MI": (-83.3, 42.3, -82.9, 42.5),
        "CA-sf": (-122.5, 37.6, -122.0, 37.9), "CO": (-105.1, 39.6, -104.8, 39.9),
    },
    "desert": {
        "AZ": (-114.5, 33.4, -113.0, 34.4), "NV": (-117.5, 38.0, -116.0, 39.0), "NM": (-107.6, 32.6, -106.4, 33.6),
        "UT": (-113.6, 39.0, -112.4, 40.0), "CA-mojave": (-117.5, 34.8, -116.2, 35.6),
        "WY": (-108.6, 41.6, -107.2, 42.4), "OR-high-desert": (-120.6, 42.8, -119.2, 43.6),
    },
}  # fmt: skip
STABLE_CLASSES = {
    "forest": (refs.CDL_FOREST, 0.92),
    "urban": (refs.CDL_DEVELOPED, 0.7),
    "desert": ({131, 152}, 0.9),
}
FLOODS = [  # name, rect, rain window. Dates from the FEMA declarations and news in docs/research/recon.md
    {"name": "Edouard-TX", "rect": (-95.4, 29.7, -93.6, 31.0), "window": (date(2026, 9, 1), date(2026, 9, 4))},
    {"name": "Indiana-central", "rect": (-86.9, 39.4, -85.0, 40.6), "window": (date(2026, 8, 11), date(2026, 8, 16))},
    {"name": "Indiana-south", "rect": (-87.6, 38.0, -85.6, 39.4), "window": (date(2026, 8, 11), date(2026, 8, 16))},
    {"name": "Ohio", "rect": (-84.6, 39.3, -82.2, 41.0), "window": (date(2026, 8, 10), date(2026, 8, 18))},
    {"name": "Isaias-FL", "rect": (-86.9, 30.1, -84.4, 31.2), "window": (date(2026, 10, 6), date(2026, 10, 11))},
    {"name": "Isaias-GA", "rect": (-84.6, 30.6, -82.0, 32.6), "window": (date(2026, 10, 8), date(2026, 10, 13))},
    {"name": "Isaias-AL", "rect": (-88.2, 30.4, -85.6, 32.2), "window": (date(2026, 10, 6), date(2026, 10, 11))},
    {"name": "WV", "rect": (-82.3, 37.2, -80.3, 38.9), "window": (date(2026, 7, 20), date(2026, 7, 24))},
    {"name": "KY", "rect": (-84.0, 36.9, -82.3, 38.3), "window": (date(2026, 6, 25), date(2026, 7, 1))},
    {"name": "TX-hill-country", "rect": (-99.9, 29.3, -98.0, 30.9), "window": (date(2026, 7, 12), date(2026, 7, 18))},
    {"name": "IA", "rect": (-96.4, 41.4, -93.6, 43.4), "window": (date(2026, 7, 1), date(2026, 7, 6))},
    {"name": "MO", "rect": (-93.6, 36.8, -90.6, 38.6), "window": (date(2026, 7, 9), date(2026, 7, 13))},
    {"name": "NM-oct", "rect": (-107.8, 33.0, -104.6, 36.0), "window": (date(2026, 10, 22), date(2026, 10, 30))},
]  # fmt: skip


# --- small geometry helpers ----------------------------------------------------------------------


def box_around(lon: float, lat: float, km: float = BOX_KM) -> list[float]:
    """[west, south, east, north] of a `km` x `km` box centred on (lon, lat)."""
    dlat = km / 2 / 111.32
    dlon = km / 2 / (111.32 * math.cos(math.radians(lat)))
    return [round(lon - dlon, 4), round(lat - dlat, 4), round(lon + dlon, 4), round(lat + dlat, 4)]


def overlap_fraction(a, b) -> float:
    """Shared area over the smaller box's area (lon/lat degrees: fine for similar latitudes)."""
    w, e, s, n = max(a[0], b[0]), min(a[2], b[2]), max(a[1], b[1]), min(a[3], b[3])
    if w >= e or s >= n:
        return 0.0
    area = lambda x: (x[2] - x[0]) * (x[3] - x[1])
    return (e - w) * (n - s) / min(area(a), area(b))


def drop_overlaps(items: list[dict], max_overlap: float = MAX_OVERLAP) -> list[dict]:
    """Keep each item whose box overlaps every earlier kept box by at most `max_overlap`."""
    kept: list[dict] = []
    for it in items:
        if all(overlap_fraction(it["bbox"], k["bbox"]) <= max_overlap for k in kept):
            kept.append(it)
    return kept


def utm_epsg(lon: float, lat: float) -> int:
    return (32600 if lat >= 0 else 32700) + int((lon + 180) // 6) + 1


# --- fires ---------------------------------------------------------------------------------------


def fire_window(p: dict) -> tuple[date, date] | None:
    """Discovery to containment (or fire-out), at least 3 and at most 45 days. A fire with
    neither date counts only if it is small enough (10,000 acres) to have burned within 14 days."""
    disc = p.get("discovered")
    if disc is None:
        return None
    end = p.get("contained") or p.get("out")
    if end is None:
        if p.get("acres", 0) > 10_000:
            return None
        end = disc + timedelta(days=14)
    return disc, min(max(end, disc + timedelta(days=3)), disc + timedelta(days=45))


def fire_boxes(geometry, acres: float, step_km: float = 3.0) -> list[list[float]]:
    """Boxes over a perimeter: the one straddling the edge most evenly (for a small fire, the one
    that takes in the most burn) and, for fires of 30,000+ acres, one wholly inside."""
    import shapely
    from shapely.geometry import box as shp_box

    poly = refs._as_polygonal(refs._to_shapely(geometry))
    if poly is None:
        return []
    w, s, e, n = poly.bounds
    mid_lat = (s + n) / 2
    dlat = step_km / 111.32
    dlon = step_km / (111.32 * math.cos(math.radians(mid_lat)))
    lons, lats = np.arange(w, e + dlon, dlon), np.arange(s, n + dlat, dlat)
    centres = [(x, y) for x in lons for y in lats] + [((w + e) / 2, mid_lat)]
    boxes = [box_around(x, y) for x, y in centres]
    cells = [shp_box(*b) for b in boxes]
    frac = shapely.area(shapely.intersection(poly, cells)) / shapely.area(cells)
    out = [boxes[int(np.argmax(np.minimum(frac, 1 - frac)))]]
    if acres >= 30_000:
        inside = [i for i in range(len(boxes)) if frac[i] > 0.98]
        if inside:
            c = poly.representative_point()
            out.append(
                boxes[
                    min(
                        inside,
                        key=lambda i: (centres[i][0] - c.x) ** 2 + (centres[i][1] - c.y) ** 2,
                    )
                ]
            )
    return out


# --- candidate generators (each returns dicts ready for `verify`) -------------------------------


def cells_from_mask(grid, mask: np.ndarray, min_count: int) -> list[tuple[int, float, float]]:
    """(count, lon, lat) for each 10 x 10 block cell with `min_count`+ True blocks, busiest first."""
    from pyproj import Transformer

    cy, cx = mask.shape[0] // 10, mask.shape[1] // 10
    counts = mask[: cy * 10, : cx * 10].reshape(cy, 10, cx, 10).sum(axis=(1, 3))
    ys, xs = np.nonzero(counts >= min_count)
    lon, lat = Transformer.from_crs(grid.epsg, 4326, always_xy=True).transform(
        grid.xmin + (xs * 10 + 5) * grid.res, grid.ymax - (ys * 10 + 5) * grid.res
    )
    return sorted(
        zip(counts[ys, xs].tolist(), np.atleast_1d(lon).tolist(), np.atleast_1d(lat).tolist()),
        reverse=True,
    )


_FS = None


def earthdata_fs():
    """One shared Earthdata-authenticated filesystem for every remote raster read."""
    global _FS
    if _FS is None:
        _FS = refs.https_fs()
    return _FS


def region_grid(rect):
    return grid_for_bbox(rect, utm_epsg((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2))


def forest_candidates(fs, per_region: int = 24) -> list[dict]:
    out = []
    for name, rect in FOREST.items():
        grid = region_grid(rect)
        loss = refs.dist_hls_loss(grid, *SCAN, fs=fs)
        cells = cells_from_mask(grid, np.nan_to_num(loss) >= 0.5, 20)
        picked = drop_overlaps([{"bbox": box_around(lo, la), "n": n} for n, lo, la in cells])[
            :per_region
        ]
        log.info("forest %s: %d cells, keeping %d", name, len(cells), len(picked))
        out += [
            {"kind": "forest_loss", "bbox": c["bbox"], "region": name, "scan_ha": c["n"]}
            for c in picked
        ]
    return out


def fire_candidates(per_fire_cap: int = 2) -> list[dict]:
    out = []
    perims = wfigs_perimeters(
        None, date(2026, 3, 15), date(2026, 10, 15), 1000, generalize_deg=0.0005
    )
    for p in perims:
        win = fire_window(p)
        if p["kind"] != "WF" or win is None or p["geometry"] is None:
            continue
        for b in fire_boxes(p["geometry"], p["acres"])[:per_fire_cap]:
            out.append(
                {
                    "kind": "fire",
                    "bbox": b,
                    "region": p["name"],
                    "window": win,
                    "geometry": p["geometry"],
                    "acres": p["acres"],
                }
            )
    return out


def _water_near(grid, day: date, offsets=(0, 3, 6)):
    for off in offsets:
        w = refs.dswx_water(grid, day + timedelta(days=off), earthdata_fs())
        if np.isfinite(w).mean() >= 0.3:
            return w
    return w


def flood_candidates(fs, per_event: int = 40) -> list[dict]:
    out = []
    for ev in FLOODS:
        grid = region_grid(ev["rect"])
        pre = refs.dswx_water(grid, ev["window"][0] - timedelta(days=12), fs=fs)
        post = _water_near(grid, ev["window"][1])
        gain = (np.nan_to_num(post) >= 0.5) & (np.nan_to_num(pre, nan=1.0) < 0.2)
        cells = cells_from_mask(grid, gain, 12)
        picked = drop_overlaps([{"bbox": box_around(lo, la), "n": n} for n, lo, la in cells])[
            :per_event
        ]
        log.info("flood %s: %d cells, keeping %d", ev["name"], len(cells), len(picked))
        out += [
            {
                "kind": "flood",
                "bbox": c["bbox"],
                "region": ev["name"],
                "window": ev["window"],
                "slack": (30, 12),
            }
            for c in picked
        ]
    return out


def cdl_cells(rect, classes, min_frac: float):
    """(fraction, lon, lat) of every 10 km cell in `rect` where `classes` fill `min_frac`+ of it."""
    from pyproj import Transformer
    from rasterio.crs import CRS
    from rasterio.warp import transform_bounds

    b = transform_bounds(CRS.from_epsg(4326), CRS.from_epsg(5070), *rect, densify_pts=21)
    for year in refs.cdl_years_to_try(None):
        got = refs._wcs_get_coverage(f"cdl_{year}", b, 100)
        if got is not None:
            break
    arr, tr, _crs = got
    ind = refs.cdl_class_indicator(arr, classes)
    cy, cx = arr.shape[0] // 100, arr.shape[1] // 100
    frac = np.nanmean(ind[: cy * 100, : cx * 100].reshape(cy, 100, cx, 100), axis=(1, 3))
    ys, xs = np.nonzero(frac >= min_frac)
    lon, lat = Transformer.from_crs(5070, 4326, always_xy=True).transform(
        tr.c + (xs * 100 + 50) * tr.a, tr.f + (ys * 100 + 50) * tr.e
    )
    return sorted(
        zip(frac[ys, xs].tolist(), np.atleast_1d(lon).tolist(), np.atleast_1d(lat).tolist()),
        reverse=True,
    )


def spread(cells, n: int, min_km: float = 25.0) -> list[tuple[float, float, float]]:
    """Up to `n` cells, best first, at least `min_km` apart (so one big field does not fill the quota)."""
    chosen: list[tuple[float, float, float]] = []
    for f, lo, la in cells:
        if all(
            math.hypot((lo - c[1]) * 111.32 * math.cos(math.radians(la)), (la - c[2]) * 111.32)
            >= min_km
            for c in chosen
        ):
            chosen.append((f, lo, la))
        if len(chosen) == n:
            break
    return chosen


def crop_candidates(per_region: int = 6) -> list[dict]:
    out = []
    for name, rect in CROPS.items():
        for f, lo, la in spread(cdl_cells(rect, refs.CDL_CULTIVATED, 0.8), per_region):
            out.append({"kind": "crops", "bbox": box_around(lo, la), "region": name, "cdl_frac": f})
    return out


def stable_candidates(per_region: int = 4) -> list[dict]:
    out = []
    for style, regions in STABLE.items():
        classes, min_frac = STABLE_CLASSES[style]
        for name, rect in regions.items():
            for f, lo, la in spread(cdl_cells(rect, classes, min_frac), per_region, min_km=15.0):
                out.append(
                    {
                        "kind": "stable",
                        "bbox": box_around(lo, la),
                        "region": f"{style}-{name}",
                        "cdl_frac": f,
                        "style": style,
                    }
                )
    return out


# --- NIFC / WFIGS download ---------------------------------------------------------------

WFIGS_URL = (
    "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
    "WFIGS_Interagency_Perimeters_YearToDate/FeatureServer/0/query"
)
_WFIGS_FIELDS = (
    "poly_IncidentName,poly_GISAcres,attr_FireDiscoveryDateTime,attr_ContainmentDateTime,"
    "attr_FireOutDateTime,poly_PolygonDateTime,attr_POOState,attr_IncidentTypeCategory,"
    "attr_UniqueFireIdentifier"
)


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

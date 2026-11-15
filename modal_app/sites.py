"""Sample ~320 ten-kilometre sites across the US for the national scorecard.

The scorecard asks one question: on states the model never saw, does fusing NISAR (L-band) and
Sentinel-1 (C-band) find real surface change better than either alone? "Real" needs an answer
key that is not radar. So every site is picked where an independent source speaks:

    forest_loss  OPERA DIST-ALERT-HLS vegetation loss under CDL forest   (optical alerts)
    fire         NIFC/WFIGS 2026 wildfire perimeters of 1,000+ acres     (mapped burn)
    flood        OPERA DSWx water that appeared between the two passes   (flood maps)
    crops        USDA CDL cultivated cropland                            (crop map)
    stable       interior forest, urban core and desert with no alerts   (negative controls)

and each must have a usable NISAR pair: two acquisitions of one stack (same track, direction,
mode and CRID) that bracket the reference window, whose footprints cover the box. The nearest
Sentinel-1 pair on a single track is recorded with its day offsets.

    python modal_app/sites.py [--kinds fire,flood] [--out PATH]      (or: modal run modal_app/sites.py)

Only catalog queries and small raster windows, so it runs fine on a laptop. Results of slow
lookups are cached in $SARSTELLAR_SITES_CACHE (default ~/.cache/sarstellar-sites).
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import requests

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:  # `python modal_app/sites.py` puts modal_app/, not the repo, first
    sys.path.insert(0, str(_ROOT))
try:
    import sarstellar  # noqa: F401
except ImportError:  # running from a checkout that was not pip-installed
    sys.path.insert(0, str(_ROOT / "core"))

from modal_app.site_candidates import (  # noqa: F401  (re-exported for callers and tests)
    MAX_OVERLAP,
    box_around,
    crop_candidates,
    drop_overlaps,
    earthdata_fs,
    fire_boxes,
    fire_candidates,
    fire_window,
    flood_candidates,
    forest_candidates,
    overlap_fraction,
    stable_candidates,
    utm_epsg,
    wfigs_perimeters,
)
from sarstellar import refs_scoring as refs
from sarstellar.grid import grid_for_bbox
from sarstellar.search import (
    GCOV_COLLECTIONS,
    _cmr_items,
    build_stacks,
    granules_on,
    pick_pair,
    search_gcov,
    search_rtc_s1,
)

log = logging.getLogger("sites")

KINDS = ("forest_loss", "fire", "flood", "crops", "stable")
TARGETS = {"forest_loss": 120, "fire": 60, "flood": 40, "crops": 40, "stable": 60}
PRIORITY = ("flood", "fire", "crops", "forest_loss", "stable")  # who keeps a contested box
US_BOUNDS = (-180.0, 17.0, -60.0, 72.0)
SLACK = (24, 24)  # days a pair may start before / end after its window
MIN_COVER = 0.9  # share of the box one pass's footprint must cover
SITES_PATH = Path(__file__).parent / "data" / "sites.json"
CACHE_DIR = Path(
    os.environ.get("SARSTELLAR_SITES_CACHE", Path.home() / ".cache" / "sarstellar-sites")
)


def validate_site(s: dict) -> list[str]:
    """Problems with a site record (an empty list means it is fine)."""
    bad = []
    if not isinstance(s.get("id"), str) or not s["id"]:
        bad.append("id")
    if s.get("kind") not in KINDS:
        bad.append("kind")
    if not (isinstance(s.get("state"), str) and len(s["state"]) == 2 and s["state"].isupper()):
        bad.append("state")
    b = s.get("bbox")
    if not (isinstance(b, list) and len(b) == 4 and b[0] < b[2] and b[1] < b[3]):
        bad.append("bbox order")
    elif not (
        US_BOUNDS[0] <= b[0]
        and b[2] <= US_BOUNDS[2]
        and US_BOUNDS[1] <= b[1]
        and b[3] <= US_BOUNDS[3]
    ):
        bad.append("bbox outside US bounds")
    elif (
        max(
            (b[3] - b[1]) * 111.32,
            (b[2] - b[0]) * 111.32 * math.cos(math.radians((b[1] + b[3]) / 2)),
        )
        > 20
    ):
        bad.append("bbox over 20 km")
    p = s.get("nisar_pair")
    if not (isinstance(p, list) and len(p) == 2 and all(isinstance(u, str) and u for u in p)):
        bad.append("nisar_pair")
    try:
        start, end = (date.fromisoformat(d) for d in s["ref_window"])
        if not start < end:
            bad.append("ref_window order")
    except (KeyError, TypeError, ValueError):
        bad.append("ref_window")
    s1 = s.get("s1")
    if s1 is not None:
        try:
            ok = (
                isinstance(s1["track"], int)
                and len(s1["dates"]) == 2
                and len(s1["offset_days"]) == 2
            )
            [date.fromisoformat(d) for d in s1["dates"]]
        except (KeyError, TypeError, ValueError):
            ok = False
        if not ok:
            bad.append("s1")
    return bad


# --- cached lookups ------------------------------------------------------------------------------


def _cached(ns: str, key: str, fn):
    path = CACHE_DIR / ns / (hashlib.md5(key.encode()).hexdigest() + ".json")
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        pass
    value = fn()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return value


def state_of(lon: float, lat: float) -> str | None:
    """USPS state code of a point, from the Census TIGERweb service."""
    url = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/0/query"
    params = {"geometry": f"{lon:.4f},{lat:.4f}", "geometryType": "esriGeometryPoint", "inSR": 4326,
              "spatialRel": "esriSpatialRelIntersects", "outFields": "STUSAB", "returnGeometry": "false", "f": "json"}  # fmt: skip

    def ask():
        for attempt in range(4):
            try:
                feats = requests.get(url, params=params, timeout=40).json().get("features", [])
                return feats[0]["attributes"]["STUSAB"] if feats else ""
            except (requests.RequestException, ValueError):
                time.sleep(2**attempt)
        raise RuntimeError("TIGERweb did not answer")

    return _cached("state", f"{lon:.3f},{lat:.3f}", ask) or None


# --- NISAR and Sentinel-1 pairs ------------------------------------------------------------------


def box_coverage(box, urs: list[str]) -> float:
    """Share of `box` covered by the union of the footprints of the granules named `urs`."""
    from shapely.geometry import Polygon
    from shapely.geometry import box as shp_box
    from shapely.ops import unary_union

    def ask():
        params = [("short_name", n) for n in GCOV_COLLECTIONS] + [("granule_ur[]", u) for u in urs]
        items = _cmr_items([*params, ("page_size", "200")])
        rings = []
        for it in items:
            geom = it["umm"]["SpatialExtent"]["HorizontalSpatialDomain"]["Geometry"]
            rings += [
                [(p["Longitude"], p["Latitude"]) for p in g["Boundary"]["Points"]]
                for g in geom["GPolygons"]
            ]
        return rings

    rings = _cached("footprint", ",".join(sorted(urs)), ask)
    if not rings:
        return 0.0
    target = shp_box(*box)
    return (
        unary_union([Polygon(r).buffer(0) for r in rings]).intersection(target).area / target.area
    )


def find_nisar_pair(box, window, slack=SLACK, min_cover=MIN_COVER) -> dict | None:
    """The best same-stack NISAR pair that brackets `window` = (start, end), or None.

    `before` is the last pass on or before `start`, `after` the first on or after `end`, within
    `slack` = (days before, days after). The tightest bracket wins (then the denser stack), and
    both passes' footprints must cover `min_cover` of the box.
    """
    start, end = window
    grans = search_gcov(
        box, start - timedelta(days=slack[0] + 1), end + timedelta(days=slack[1] + 1)
    )
    found = []
    for stack in build_stacks(grans):
        try:
            pre, post = pick_pair(stack, (start, end))
        except ValueError:
            continue
        d0, d1 = pre.start.date(), post.start.date()
        s0, s1 = (start - d0).days, (d1 - end).days
        if 0 <= s0 <= slack[0] and 0 <= s1 <= slack[1]:
            found.append(
                (
                    (s0 + s1, -len(stack.dates), stack.track, stack.direction),
                    stack,
                    d0,
                    d1,
                    (s0, s1),
                )
            )
    for _key, stack, d0, d1, slack_days in sorted(found, key=lambda f: f[0]):
        got = _covered_pair(box, stack, d0, d1, slack_days, min_cover)
        if got:
            return got
    return None


def _covered_pair(box, stack, d0: date, d1: date, slack_days, min_cover: float) -> dict | None:
    """The pair record for passes `d0` and `d1` of `stack`, if both footprints cover the box."""
    picks = []
    for day in (d0, d1):
        frames = granules_on(stack, day)
        if box_coverage(box, [g.ur for g in frames]) < min_cover:
            return None
        picks.append(frames[0])
    return {
        "nisar_pair": [picks[0].ur, picks[1].ur], "dates": [d0.isoformat(), d1.isoformat()],
        "track": stack.track, "direction": stack.direction, "crid": stack.crid,
        "slack_days": list(slack_days),
    }  # fmt: skip


def find_season_pair(
    box, lo=date(2026, 5, 1), hi=date(2026, 11, 12), gap=(36, 120), min_cover=MIN_COVER
) -> dict | None:
    """A same-stack pair of passes inside [lo, hi] for a site with no event, or None.

    For forest, crop and control sites the reference window is the pair's own interval, so any two
    passes `gap` days apart will do; the pair nearest 84 days (seven repeat cycles) from the
    densest stack wins. Both footprints must cover `min_cover` of the box.
    """
    found = []
    for stack in build_stacks(search_gcov(box, lo, hi)):
        days = stack.dates
        pairs = [
            (abs((b - a).days - 84), a, b)
            for i, a in enumerate(days)
            for b in days[i + 1 :]
            if gap[0] <= (b - a).days <= gap[1]
        ]
        if pairs:
            _score, a, b = min(pairs)
            found.append(((_score, -len(days), stack.track, stack.direction), stack, a, b))
    for _key, stack, d0, d1 in sorted(found, key=lambda f: f[0]):
        got = _covered_pair(box, stack, d0, d1, (0, 0), min_cover)
        if got:
            return got
    return None


def find_s1_pair(box, pre: date, post: date, max_days: int = 6) -> dict | None:
    """One Sentinel-1 track seen near both NISAR dates, with its day offsets, or None."""

    def nearest(around):
        best: dict[int, dict] = {}
        for sc in search_rtc_s1(box, around, max_days):
            if sc["track"] not in best or abs((sc["date"] - around).days) < abs(
                (best[sc["track"]]["date"] - around).days
            ):
                best[sc["track"]] = sc
        return best

    a, b = nearest(pre), nearest(post)
    shared = [
        (abs((a[t]["date"] - pre).days) + abs((b[t]["date"] - post).days), t) for t in a if t in b
    ]
    if not shared:
        return None
    _score, t = min(shared)
    return {
        "track": t, "dates": [a[t]["date"].isoformat(), b[t]["date"].isoformat()],
        "offset_days": [(a[t]["date"] - pre).days, (b[t]["date"] - post).days],
    }  # fmt: skip


# --- verification: reference answers + pairs -----------------------------------------------------


def _pair_for(c: dict) -> tuple[dict, tuple[date, date]] | None:
    """A NISAR pair for a candidate: its event window, or the first growing-season window that works."""
    if "window" in c:
        pair = find_nisar_pair(c["bbox"], c["window"], c.get("slack", SLACK))
        return (pair, c["window"]) if pair else None
    pair = find_season_pair(c["bbox"])
    if pair:  # the window is the pair's own interval: labels cover exactly what the radar saw
        return pair, tuple(date.fromisoformat(d) for d in pair["dates"])
    return None


def _reference(c: dict, grid, window, pair, perims) -> int | None:
    """Hectares of independent reference evidence in the box (None if the site fails its kind's test)."""
    kind = c["kind"]
    if kind == "forest_loss":
        loss = np.nan_to_num(refs.dist_hls_loss(grid, *window, fs=earthdata_fs()))
        ref = (loss >= 0.5) & (np.nan_to_num(refs.cdl_fraction(grid, refs.CDL_FOREST)) >= 0.5)
        return int(ref.sum()) if ref.sum() >= 20 else None
    if kind == "fire":
        n = int(refs.nifc_mask(grid, [c["geometry"]]).sum())
        return n if n >= 20 else None
    if kind == "flood":
        d0, d1 = (date.fromisoformat(d) for d in pair["dates"])
        pre, post = (
            refs.dswx_water(grid, d0, earthdata_fs()),
            refs.dswx_water(grid, d1, earthdata_fs()),
        )
        gain = (np.nan_to_num(post) >= 0.5) & (np.nan_to_num(pre, nan=1.0) < 0.2)
        return int(gain.sum()) if gain.sum() >= 12 and np.isfinite(post).mean() >= 0.5 else None
    if kind == "crops":
        crop = refs.cdl_crop(grid)
        return int(crop.sum()) if crop.mean() >= 0.7 else None
    loss = np.nan_to_num(
        refs.dist_hls_loss(grid, *window, fs=earthdata_fs())
    )  # stable: no alerts/fire
    from shapely.geometry import box as shp_box

    near_fire = any(shp_box(*c["bbox"]).intersects(g) for g in perims)
    return 0 if (loss >= 0.5).sum() == 0 and loss.mean() < 0.002 and not near_fire else None


def verify(c: dict, perims=()) -> dict | None:
    """Turn a candidate into a site dict, or None if it fails any test. Never raises."""
    try:
        got = _pair_for(c)
        if got is None:
            return None
        pair, window = got
        lon, lat = (c["bbox"][0] + c["bbox"][2]) / 2, (c["bbox"][1] + c["bbox"][3]) / 2
        state = state_of(lon, lat)
        if not state:
            return None
        grid = grid_for_bbox(c["bbox"], utm_epsg(lon, lat))
        ref = _reference(c, grid, window, pair, perims)
        if ref is None:
            return None
        d0, d1 = (date.fromisoformat(d) for d in pair["dates"])
        return {
            "kind": c["kind"], "bbox": c["bbox"], "state": state, "nisar_pair": pair["nisar_pair"],
            "s1": find_s1_pair(c["bbox"], d0, d1), "ref_window": [window[0].isoformat(), window[1].isoformat()],
            "meta": {"region": c["region"], "ref_ha": ref, "track": pair["track"], "direction": pair["direction"],
                     "crid": pair["crid"], "pair_dates": pair["dates"], "slack_days": pair["slack_days"]},
        }  # fmt: skip
    except Exception as exc:  # noqa: BLE001  one flaky candidate must not sink a 30-minute run
        log.warning(
            "candidate %s %s failed: %s: %s",
            c["kind"],
            c["bbox"],
            type(exc).__name__,
            str(exc)[:100],
        )
        return None


def balanced(items: list[dict], target: int) -> list[dict]:
    """`target` items, taken best-first but round-robin across states so no state dominates."""
    by_state: dict[str, list[dict]] = {}
    for it in items:
        by_state.setdefault(it["state"], []).append(it)
    out: list[dict] = []
    while len(out) < target and any(by_state.values()):
        for state in sorted(by_state, key=lambda s: -len(by_state[s])):
            if by_state[state] and len(out) < target:
                out.append(by_state[state].pop(0))
    return out


def build_sites(kinds=KINDS, workers: int = 6) -> list[dict]:
    fs = earthdata_fs()
    every = wfigs_perimeters(None, date(2026, 1, 1), date(2026, 12, 31), 1000, generalize_deg=0.001)
    perims = [
        g
        for p in every
        if p["geometry"] and (g := refs._as_polygonal(refs._to_shapely(p["geometry"])))
    ]
    gens = {"forest_loss": lambda: forest_candidates(fs), "fire": fire_candidates, "flood": lambda: flood_candidates(fs),
            "crops": crop_candidates, "stable": stable_candidates}  # fmt: skip
    pools: dict[str, list[dict]] = {}
    for kind in kinds:
        cands = gens[kind]()
        log.info("%s: %d candidates", kind, len(cands))
        with ThreadPoolExecutor(workers) as ex:
            ok = [s for s in ex.map(lambda c: verify(c, perims), cands) if s]
        pools[kind] = sorted(ok, key=lambda s: -s["meta"]["ref_ha"])
        log.info("%s: %d verified in %d states", kind, len(ok), len({s["state"] for s in ok}))
    ordered = [s for k in PRIORITY if k in pools for s in pools[k]]
    kept = drop_overlaps(ordered)
    final = [
        s
        for k in KINDS
        if k in pools
        for s in balanced([x for x in kept if x["kind"] == k], TARGETS[k])
    ]
    counter: dict[tuple[str, str], int] = {}
    for s in final:
        key = (s["kind"], s["state"])
        counter[key] = counter.get(key, 0) + 1
        s["id"] = f"{s['kind'].replace('_', '-')}-{s['state'].lower()}-{counter[key]:02d}"
    return [
        {k: s[k] for k in ("id", "kind", "bbox", "state", "nisar_pair", "s1", "ref_window", "meta")}
        for s in final
    ]


def main(argv: list[str] | None = None) -> None:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--kinds", default=",".join(KINDS))
    ap.add_argument("--out", default=str(SITES_PATH))
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    result = build_sites(tuple(args.kinds.split(",")))
    problems = [(s["id"], validate_site(s)) for s in result if validate_site(s)]
    if problems:
        raise SystemExit(f"invalid sites: {problems[:5]}")
    Path(args.out).write_text(json.dumps(result, indent=1) + "\n")
    counts = {k: sum(s["kind"] == k for s in result) for k in KINDS}
    log.info(
        "wrote %d sites to %s: %s; %d states",
        len(result),
        args.out,
        counts,
        len({s["state"] for s in result}),
    )


try:  # `modal run modal_app/sites.py` runs this locally: catalog queries need no cloud machine
    import modal

    app = modal.App("sarstellar-sites")

    @app.local_entrypoint()
    def run() -> None:
        main([])

except ImportError:  # modal is optional here
    pass

if __name__ == "__main__":
    main()

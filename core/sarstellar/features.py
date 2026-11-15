"""Shared block features: everything the app and the scorecard compute per 1-ha block.

`block_features(bbox, dates)` searches NISAR, picks the best stack, reads it as 1-ha block means
(plus the nearest Sentinel-1 pair, if any), and returns a `BlockSet`: the box's grid, the dates
used, pre/post levels, scene-corrected relative changes in dB, omnibus p-values for L-band (100 m
and 30 m lattice) and C-band, and the first-change index. `run_box` (the app) and the scorecard
both build on it, so a number shown to a user and a number in the scorecard are the same number.

Statistics follow `detect`: one stable mask per sensor, dates normalised on stable blocks, the
ENL estimated from the data. The ENL is estimated per NLCD stratum that has at least 200 stable
blocks and falls back to the scene-wide ENL elsewhere (Ruling R13); each stratum is also
date-normalised on its own stable blocks, so the estimate and the test see the same data.

`TooFewBlocks` and `NoStableBlocks` from `detect` propagate for NISAR (`run_box` turns them into
messages). For the optional Sentinel-1 pair they only switch C off (`s1` is None).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np

from . import detect, read, refs, search
from .grid import grid_for_bbox
from .types import Granule, Grid, NoUsablePasses, Stack

log = logging.getLogger(__name__)

__all__ = ["MAX_DATES", "BlockSet", "NoUsablePasses", "block_features"]

WINDOW_DAYS = 365  # default series: the last 12 months
MAX_DATES = 12  # more passes than this are thinned (first and last always kept)
S1_MAX_DAYS = 6  # a Sentinel-1 scene must be this close to the NISAR first / last date
MIN_VALID_FRAC = 0.5  # a block needs half its pixels valid on every date
MIN_STRATUM_BLOCKS = detect.MIN_BLOCKS  # stable blocks a stratum needs for its own ENL
_L_KEYS = ("HH", "HV", "HH30", "HV30")
_ProgressFn = Callable[[float, str], None]


@dataclass
class BlockSet:
    """Per-block features for one box. Arrays are [ny, nx]; NaN marks a block with no data.

    `dates` are the NISAR dates used (oldest first); `pre_*` is the first, `post_*` the last.
    `rel_d*` is last minus first in dB with the stable blocks' median shift removed. `p_*` is the
    omnibus p over that sensor's whole series (Bonferroni-min over its two bands);
    `change_idx_*` is the 0-based index of the first date after the change, -1 if none. The C
    series has two dates (the Sentinel-1 pair), so its index is 0 or 1 at most.

    `s1` is None when no usable Sentinel-1 pair exists, else {"track": int, "dates": [date, date],
    "offset_days": [int, int]} where offsets are Sentinel-1 minus NISAR date for the first and
    last NISAR date. `enl` holds the scene-wide ENL per band; `enl_by_stratum[band][stratum]`
    the ENL of each stratum that had enough stable blocks. `newer_validated_dates` are passes on
    the same track and direction, in other processing releases (CRIDs), after the series ends.
    """

    grid: Grid
    stack: Stack
    dates: list[date]
    s1: dict[str, Any] | None
    newer_validated_dates: list[date]
    landcover: np.ndarray
    valid: np.ndarray
    pre_HH: np.ndarray
    pre_HV: np.ndarray
    post_HH: np.ndarray
    post_HV: np.ndarray
    rel_dHH: np.ndarray
    rel_dHV: np.ndarray
    rel_dVV: np.ndarray
    rel_dVH: np.ndarray
    p_L: np.ndarray
    p_C: np.ndarray
    p_L30: np.ndarray
    change_idx_L: np.ndarray
    change_idx_C: np.ndarray
    enl: dict[str, float]
    enl_by_stratum: dict[str, dict[str, float]]


# --- small helpers ------------------------------------------------------------------------------


def _today() -> date:
    return date.today()


def _to_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _window(dates) -> tuple[date, date]:
    if dates is None:
        end = _today()
        return end - timedelta(days=WINDOW_DAYS), end
    start, end = sorted(_to_date(d) for d in dates)
    return start, end


def _tick(progress: _ProgressFn | None, fraction: float, message: str) -> None:
    if progress is not None:
        progress(fraction, message)


def _db(x: np.ndarray) -> np.ndarray:
    return 10.0 * np.log10(x)  # inputs are positive or NaN


def _thin(days: Sequence[date], limit: int) -> list[date]:
    """At most `limit` dates, evenly spread, always keeping the first and the last."""
    if len(days) <= limit:
        return list(days)
    keep = np.unique(np.round(np.linspace(0, len(days) - 1, limit)).astype(int))
    return [days[i] for i in keep]


# --- NISAR: search, read, composite -------------------------------------------------------------


def _read_sequential(granules: Sequence[Granule], bbox, grid: Grid | None):
    """Default `read_passes`: one granule after another, all on the first granule's grid.

    A granule in another UTM zone, or one the window does not reach, is skipped once a grid
    exists; `block_features` then drops a date that has no pass left.
    """
    fs = read.https_fs()
    out = []
    for g in granules:
        try:
            meta, blocks, grid = read.read_gcov_blocks(g.url, bbox, fs, grid)
        except ValueError as exc:
            if "does not overlap" in str(exc) or ("EPSG differs" in str(exc) and out):
                log.warning("skipping %s: %s", g.ur, exc)
                continue
            raise
        out.append((meta, blocks))
    return out


def _no_passes(start: date, end: date) -> NoUsablePasses:
    return NoUsablePasses(
        f"No calibrated NISAR passes cover this box between {start} and {end}."
    )


def _composite(
    passes, bbox, start: date, end: date
) -> tuple[Grid, dict[date, dict[str, np.ndarray]]]:
    """Group passes by date on one grid. Frames of the same date fill each other's gaps.

    The grid is the covering grid in the first pass's UTM zone; a pass in another zone is
    dropped, so no series ever mixes two projections.
    """
    if not passes:
        raise _no_passes(start, end)
    epsg = int(passes[0][0]["epsg"])
    grid = grid_for_bbox(bbox, epsg)
    by_day: dict[date, dict[str, np.ndarray]] = {}
    for meta, blocks in passes:
        if int(meta["epsg"]) != epsg:
            log.warning("dropping %s: UTM zone %s differs from %s", meta.get("granule"),
                        meta["epsg"], epsg)
            continue
        got = {k: np.asarray(blocks[k], dtype=float) for k in (*_L_KEYS, "valid_frac")}
        for k, v in got.items():
            if v.shape != grid.shape:
                raise ValueError(f"block array {k} is {v.shape}, grid is {grid.shape}")
        day = _to_date(meta["date"])
        if day not in by_day:
            by_day[day] = got
            continue
        have = by_day[day]
        for k in _L_KEYS:
            have[k] = np.where(np.isfinite(have[k]), have[k], got[k])
        have["valid_frac"] = np.maximum(have["valid_frac"], got["valid_frac"])
    if len(by_day) < 2:
        raise _no_passes(start, end)
    return grid, by_day


def _newer_validated(stacks: Sequence[Stack], chosen: Stack, last: date) -> list[date]:
    """Dates on the chosen track and direction, in other CRIDs, after the series ends."""
    later = {
        d
        for s in stacks
        if s.track == chosen.track and s.direction == chosen.direction and s.crid != chosen.crid
        for d in s.dates
        if d > last
    }
    return sorted(later)


# --- statistics ---------------------------------------------------------------------------------


def _all_valid(series: Sequence[np.ndarray]) -> np.ndarray:
    return np.logical_and.reduce([np.all(np.isfinite(s) & (s > 0), axis=0) for s in series])


def _delta_db(series: np.ndarray) -> np.ndarray:
    return _db(series[-1]) - _db(series[0])  # last minus first, NaN where either is missing


def _omnibus(bands: dict[str, np.ndarray], stable: np.ndarray, landcover: np.ndarray):
    """Omnibus p and change index for a band set, with per-stratum ENL and date normalisation.

    Returns (p, change_idx, scene_enl, enl_by_stratum). Raises `TooFewBlocks` /
    `NoStableBlocks` from `detect` when the scene-wide ENL cannot be estimated.
    """
    series = list(bands.values())
    ok = _all_valid(series) & stable
    strata = [
        s for s in np.unique(landcover)
        if s and int((ok & (landcover == s)).sum()) >= MIN_STRATUM_BLOCKS
    ]
    scene: dict[str, float] = {}
    by_stratum: dict[str, dict[str, float]] = {}
    normalised, maps = [], []
    for name, s in bands.items():
        scene[name] = detect.estimate_enl(s, stable)
        norm = detect.normalise_dates(s, stable)
        enl_map = np.full(stable.shape, scene[name])
        for stratum in strata:
            inside = landcover == stratum
            only = np.where(inside, s, np.nan)
            try:
                enl_s = detect.estimate_enl(only, stable & inside)
                norm_s = detect.normalise_dates(only, stable & inside)
            except (detect.TooFewBlocks, detect.NoStableBlocks):
                continue  # this stratum keeps the scene-wide ENL and normalisation
            enl_map[inside] = enl_s
            norm[:, inside] = norm_s[:, inside]
            by_stratum.setdefault(name, {})[str(stratum)] = enl_s
        normalised.append(norm)
        maps.append(enl_map)
    p, change_idx = detect.omnibus(normalised, maps)
    return p, change_idx, scene, by_stratum


# --- Sentinel-1 ---------------------------------------------------------------------------------


def _pick_s1_pair(bbox, first: date, last: date):
    """The Sentinel-1 track with a dual-pol scene within 6 days of both NISAR end dates.

    Returns (meta, scene_first, scene_last), or None. Closest in total days wins, then the
    lower track number; the two scenes must be different days.
    """
    def nearest(around: date) -> dict[int, dict]:
        scenes = [s for s in search.search_rtc_s1(bbox, around, S1_MAX_DAYS)
                  if s["urls_vv"] and s["urls_vh"]]
        best: dict[int, dict] = {}
        for s in scenes:  # a track may have several dates in the window: keep the nearest
            cur = best.get(s["track"])
            if cur is None or abs((s["date"] - around).days) < abs((cur["date"] - around).days):
                best[s["track"]] = s
        return best

    a, b = nearest(first), nearest(last)
    options = []
    for track in sorted(set(a) & set(b)):
        if a[track]["date"] == b[track]["date"]:
            continue
        offsets = [(a[track]["date"] - first).days, (b[track]["date"] - last).days]
        options.append((sum(abs(o) for o in offsets), track, offsets))
    if not options:
        return None
    _, track, offsets = min(options)
    meta = {"track": track, "dates": [a[track]["date"], b[track]["date"]], "offset_days": offsets}
    return meta, a[track], b[track]


def _read_s1(scenes, grid: Grid) -> dict[str, np.ndarray]:
    """Mosaic the two scenes onto the grid: {"VV": [2, ny, nx], "VH": [2, ny, nx]}, linear power.

    A block is kept only if VV and VH are finite and > 0 on both dates."""
    fs = read.https_fs()
    pols: dict[str, list[np.ndarray]] = {"VV": [], "VH": []}
    for scene in scenes:
        got = read.read_rtc_to_grid(list(scene["urls_vv"]) + list(scene["urls_vh"]), grid, fs)
        for pol, scenes_of_pol in pols.items():
            scenes_of_pol.append(np.asarray(got[pol], dtype=float))
    series = {pol: np.stack(v) for pol, v in pols.items()}
    ok = _all_valid(list(series.values()))  # every band finite and > 0 on both dates
    return {pol: np.where(ok, s, np.nan) for pol, s in series.items()}


# --- the entry point ----------------------------------------------------------------------------


def block_features(
    bbox,
    dates=None,
    *,
    read_passes: Callable | None = None,
    s1: bool = True,
    progress: _ProgressFn | None = None,
) -> BlockSet:
    """Compute the `BlockSet` for a lon/lat box.

    `dates` is (start, end) as dates or ISO strings, default the last 12 months. The series is
    every date of the best stack in that interval (most dates, then most recent), thinned to
    `MAX_DATES`. Raises `NoUsablePasses` when no stack has two dates.

    `read_passes(granules, bbox, grid) -> [(meta, blocks)]` reads every granule of the series
    (several per date when frames share a date) as `read.read_gcov_blocks` would; `grid` is None
    on the call (the first file decides the UTM zone). `meta` needs "date" and "epsg". The
    default reads sequentially. `progress(fraction, message)` reports 0.1 (searched), 0.2 to 0.7
    (NISAR reads), 0.75 (Sentinel-1), 0.8 (testing) and 0.85 (done); `run_box` continues from 0.85.
    """
    start, end = _window(dates)
    _tick(progress, 0.05, "Searching for NISAR passes")
    found = search.search_gcov(bbox, start, end)
    in_window = [g for g in found if start <= g.start.date() <= end]
    stacks = search.build_stacks(in_window)
    usable = [s for s in stacks if len(s.dates) >= 2]
    if not usable:
        raise _no_passes(start, end)
    stack = usable[0]
    wanted = _thin(stack.dates, MAX_DATES)
    granules = [g for d in wanted for g in search.granules_on(stack, d)]
    _tick(progress, 0.1, f"Found {len(wanted)} NISAR passes")

    _tick(progress, 0.2, f"Reading {len(granules)} NISAR granules")
    passes = (read_passes or _read_sequential)(granules, bbox, None)
    _tick(progress, 0.7, "Read the NISAR passes")
    grid, by_day = _composite(passes, bbox, start, end)
    days = sorted(by_day)
    newer = _newer_validated(search.build_stacks(found), stack, days[-1])

    landcover = np.asarray(refs.nlcd(grid))
    if landcover.shape != grid.shape:
        raise ValueError(f"land cover {landcover.shape} does not match the grid {grid.shape}")

    def series(key: str) -> np.ndarray:
        return np.stack([by_day[d][key] for d in days])

    frac = series("valid_frac")
    hh, hv, hh30, hv30 = (series(k) for k in _L_KEYS)
    valid = np.all(frac >= MIN_VALID_FRAC - 1e-9, axis=0) & _all_valid([hh, hv])
    ok30 = valid & _all_valid([hh30, hv30])
    hh, hv = (np.where(valid, a, np.nan) for a in (hh, hv))
    hh30, hv30 = (np.where(ok30, a, np.nan) for a in (hh30, hv30))

    _tick(progress, 0.75, "Finding Sentinel-1 passes")
    c_series = None
    s1_meta = None
    if s1:
        pair = _pick_s1_pair(bbox, days[0], days[-1])
        if pair is not None:
            s1_meta, *scenes = pair
            c_series = _read_s1(scenes, grid)

    _tick(progress, 0.8, "Testing for change")
    stable = detect.stable_mask([_delta_db(hh), _delta_db(hv)])
    rel_hh = detect.relative_delta(_delta_db(hh), stable)
    rel_hv = detect.relative_delta(_delta_db(hv), stable)
    p_l, idx_l, enl, by_stratum = _omnibus({"HH": hh, "HV": hv}, stable, landcover)
    p_l30, _, enl30, by30 = _omnibus({"HH30": hh30, "HV30": hv30}, stable, landcover)
    enl.update(enl30)
    by_stratum.update(by30)

    def no_c():  # C-band off: NaN p and changes, no change index
        return (*(np.full(grid.shape, np.nan) for _ in range(3)),
                np.full(grid.shape, -1, dtype=np.int64))

    p_c, rel_vv, rel_vh, idx_c = no_c()
    if c_series is not None:
        try:
            d_vv, d_vh = (_delta_db(c_series[k]) for k in ("VV", "VH"))
            stable_c = detect.stable_mask([d_vv, d_vh])
            rel_vv = detect.relative_delta(d_vv, stable_c)
            rel_vh = detect.relative_delta(d_vh, stable_c)
            p_c, idx_c, enl_c, by_c = _omnibus(c_series, stable_c, landcover)
            enl.update(enl_c)
            by_stratum.update(by_c)
        except (detect.TooFewBlocks, detect.NoStableBlocks) as exc:
            log.warning("Sentinel-1 pair unusable, C-band off: %s", exc)
            s1_meta = None
            p_c, rel_vv, rel_vh, idx_c = no_c()
    _tick(progress, 0.85, "Change test done")

    return BlockSet(
        grid=grid,
        stack=stack,
        dates=days,
        s1=s1_meta,
        newer_validated_dates=newer,
        landcover=landcover,
        valid=valid,
        pre_HH=_db(hh[0]),
        pre_HV=_db(hv[0]),
        post_HH=_db(hh[-1]),
        post_HV=_db(hv[-1]),
        rel_dHH=rel_hh,
        rel_dHV=rel_hv,
        rel_dVV=rel_vv,
        rel_dVH=rel_vh,
        p_L=p_l,
        p_C=p_c,
        p_L30=p_l30,
        change_idx_L=idx_l,
        change_idx_C=idx_c,
        enl=enl,
        enl_by_stratum=by_stratum,
    )

"""`run_box`: one lon/lat box in, one `Result` out.

The heavy lifting is shared: `features.block_features` searches NISAR, reads the stack (and the
nearest Sentinel-1 pair) as 1-ha blocks and runs the change test. This module turns those block
arrays into what a user sees: which blocks changed per sensor (BH-FDR q = 0.05 and at least 2 dB),
connected change areas of 3 ha or more, per-area numbers with intervals, the cause rules, map
overlays, short plain-language text and the "who lives here" tracts.

Decisions worth knowing:

* An area's land cover is the NLCD group most of its blocks share, written as the NLCD class name
  the rules match on. The detector's "wetland" group (woody and emergent herbaceous merged) is
  written "Wetland (treated as woody)" so the rules take their forest path, the only wetland path
  they have. The same goes for crops: the NLCD crop group stands in for a Cropland Data Layer mask.
* `frac_significant` is the share of an area's blocks that pass the FDR test in the sensor(s) that
  flagged it (the mean of the two for "both"). `confidence` is that share times the effect size
  (the largest band change over 6 dB), placed inside the band of its High/Medium/Low label.
* Weather is looked up once, at the box centre on the last NISAR date: the model grid is about
  9 km, so a box of at most 20 km would get nearly the same answer anywhere inside it.
* No terrain model is used, so `hand_m` and `slope_deg` stay None (the landslide rule and the
  flat-ground wetting rule need them and cannot fire) and `downslope_shape` is False.
"""

from __future__ import annotations

import base64
import io
import logging
import os
from collections.abc import Callable

import numpy as np
from PIL import Image
from shapely import make_valid
from shapely.geometry import shape
from shapely.ops import unary_union

from . import areas as areas_mod
from . import detect, explain, features, refs, render
from .rules import AreaStats, classify
from .types import ChangeArea, NoUsablePasses, Result

log = logging.getLogger(__name__)

__all__ = ["NO_S1_MESSAGE", "NO_VALID_MESSAGE", "NoUsablePasses", "explain_areas", "run_box"]

Q = 0.05  # BH false discovery rate
MIN_DB = 2.0  # smallest |relative change| that counts as changed
MIN_HA = 3  # smallest change area
MIN_VALID_FRACTION = 0.2  # a box needs this share of valid blocks
EXPLAIN_MAX_AREAS = 10  # the LLM words at most this many areas (the largest)
EXPLAIN_TIMEOUT_S = 5.0
BREAKER_FAILURES = 2  # consecutive LLM failures before every other area gets the template
FIRMS_MAX_AREAS = 25  # FIRMS lookups (one request each) for at most this many areas
BOOTSTRAP = 200  # resamples for the median's interval
EFFECT_FULL_DB = 6.0

NO_VALID_MESSAGE = "Most of this box has no valid radar data."
NO_S1_MESSAGE = "No Sentinel-1 pass within 6 days; showing NISAR only."

_AGREE_CODE = {"L": render.AGREE_L, "both": render.AGREE_BOTH, "C": render.AGREE_C}
_LANDCOVER_NAME = {  # refs.nlcd group -> the class name the rules match on
    "forest": "Forest", "shrub_grass": "Shrub/grass", "crops": "Cropland",
    "wetland": "Wetland (treated as woody)", "developed": "Developed", "water": "Open water",
    "barren": "Barren",
}  # fmt: skip
_BANDS = ("HH", "HV", "VV", "VH")
_CONFIDENCE_BAND = {"High": (0.8, 0.2), "Medium": (0.5, 0.29), "Low": (0.0, 0.49)}

PngSink = Callable[[str, bytes], str]


# --- overlays -----------------------------------------------------------------------------------


def _data_url(name: str, png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _blank_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


def _shared_stretch(*arrays: np.ndarray) -> tuple[float | None, float | None]:
    """One grey stretch (2nd to 98th percentile) for the before and after images."""
    vals = np.concatenate([a[np.isfinite(a)] for a in arrays])
    if vals.size == 0:
        return None, None
    lo, hi = np.percentile(vals, (2.0, 98.0))
    return float(lo), float(hi)


def _overlays(bs, masks_and_agreement, publish: PngSink) -> dict:
    grid = bs.grid
    agree = np.full(grid.shape, np.nan)
    for mask, agreement in masks_and_agreement:  # paint with the area's agreement, like its polygon
        agree[mask] = _AGREE_CODE[agreement]
    vmin, vmax = _shared_stretch(bs.pre_HV, bs.post_HV)
    shots = {
        "change": (agree, "agreement", {}),
        "l": (bs.rel_dHV, "delta", {}),  # L-band cross-pol: the vegetation channel
        "c": (bs.rel_dVH, "delta", {}),  # C-band cross-pol
        "before": (bs.pre_HV, "backscatter", {"vmin": vmin, "vmax": vmax}),
        "after": (bs.post_HV, "backscatter", {"vmin": vmin, "vmax": vmax}),
    }
    out: dict = {}
    bounds = None
    for name, (values, kind, kw) in shots.items():
        png, bounds = render.render_png(values, grid, kind, **kw)
        out[f"{name}_png"] = publish(name, png)
    out["bounds"] = bounds
    return out


def _blank_overlays(bbox, publish: PngSink) -> dict:
    w, s, e, n = (float(v) for v in bbox)
    out = {f"{name}_png": publish(name, _blank_png())
           for name in ("change", "l", "c", "before", "after")}
    out["bounds"] = [[w, n], [e, n], [e, s], [w, s]]
    return out


# --- per-area numbers ---------------------------------------------------------------------------


def _finite(arr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    v = arr[mask]
    return v[np.isfinite(v)]


def _median(arr: np.ndarray, mask: np.ndarray) -> float | None:
    v = _finite(arr, mask)
    return float(np.median(v)) if v.size else None


def _median_ci(arr: np.ndarray, mask: np.ndarray) -> tuple[float, float] | None:
    """95% percentile-bootstrap interval of the median over the area's blocks."""
    v = _finite(arr, mask)
    if v.size < 2:
        return None
    rng = np.random.default_rng(0)  # same area, same interval
    meds = np.median(v[rng.integers(0, v.size, (BOOTSTRAP, v.size))], axis=1)
    lo, hi = np.percentile(meds, (2.5, 97.5))
    return float(lo), float(hi)


def _landcover(bs, mask: np.ndarray) -> str:
    vals = bs.landcover[mask]
    vals = vals[vals != ""]
    if vals.size == 0:
        return ""
    names, counts = np.unique(vals, return_counts=True)
    return str(names[counts.argmax()])  # the group; mapped to a class name by the caller


def _change_date(bs, mask, agreement, changed_L, changed_C) -> str | None:
    """Date of the first pass after the change: NISAR's when it saw the area, else Sentinel-1's."""
    if agreement in ("L", "both"):
        idx, days = bs.change_idx_L[mask & changed_L], bs.dates
    else:
        idx, days = bs.change_idx_C[mask & changed_C], (bs.s1 or {}).get("dates", [])
    idx = idx[(idx >= 0) & (idx < len(days))]
    if idx.size == 0:
        return None
    return days[int(np.bincount(idx).argmax())].isoformat()


def _series(bs, mask: np.ndarray) -> dict:
    """One timeline of every NISAR and Sentinel-1 date; each band is null where it has no pass."""
    nisar = [d.isoformat() for d in bs.dates]
    c_days = [d.isoformat() for d in bs.s1["dates"]] if bs.s1 and bs.series_C else []
    days = sorted(set(nisar) | set(c_days))
    out: dict = {"dates": days, **{b: [None] * len(days) for b in _BANDS}}

    def put(band: str, day: str, cube: np.ndarray, t: int) -> None:
        v = _median(cube[t], mask)
        out[band][days.index(day)] = None if v is None else round(v, 2)

    for band in ("HH", "HV"):
        if bs.series_L:
            for t, day in enumerate(nisar):
                put(band, day, bs.series_L[band], t)
    for band in ("VV", "VH"):
        for t, day in enumerate(c_days):
            put(band, day, bs.series_C[band], t)
    return out


def _confidence(label: str, frac: float | None, effect_db: float | None) -> float:
    """0..1, inside the band of `label` (High 0.8-1, Medium 0.5-0.79, Low under 0.5)."""
    base = min(max(frac or 0.0, 0.0), 1.0) * min(abs(effect_db or 0.0) / EFFECT_FULL_DB, 1.0)
    lo, span = _CONFIDENCE_BAND[label]
    return round(lo + span * base, 2)


def _weather(bs, bbox) -> dict:
    w, s, e, n = bbox
    return refs.weather((w + e) / 2, (s + n) / 2, bs.dates[-1])


def _fire_geometry(perimeters):
    try:
        return unary_union([make_valid(shape(p["geometry"])) for p in perimeters]) or None
    except Exception as exc:  # noqa: BLE001 - a malformed perimeter only loses fire evidence
        log.warning("fire perimeters unusable: %s: %s", type(exc).__name__, exc)
        return None


def _in_perimeter(fire, geometry) -> bool:
    if fire is None:
        return False
    g = shape(geometry)
    return bool(g.area > 0 and fire.intersection(g).area / g.area >= 0.5)


def _p_arrays(bs, agreement: str) -> list[np.ndarray]:
    """The omnibus p arrays of the sensor(s) that flagged an area."""
    return {"L": [bs.p_L], "C": [bs.p_C]}.get(agreement, [bs.p_L, bs.p_C])


def _build_area(n: int, geometry, mask, agreement, bs, ctx: dict) -> ChangeArea:
    sig_L, sig_C = ctx["sig_L"][mask].mean(), ctx["sig_C"][mask].mean()
    frac = {"L": sig_L, "C": sig_C}.get(agreement, (sig_L + sig_C) / 2)
    rel = {"HH": bs.rel_dHH, "HV": bs.rel_dHV, "VV": bs.rel_dVV, "VH": bs.rel_dVH}
    deltas = {b: _median(a, mask) for b, a in rel.items()}
    group = _landcover(bs, mask)
    drop = [d for d in (deltas["HV"], deltas["VH"]) if d is not None and d <= -MIN_DB]
    stats = AreaStats(
        dHH=deltas["HH"], dHV=deltas["HV"], dVV=deltas["VV"], dVH=deltas["VH"],
        ci={b: _median_ci(a, mask) for b, a in rel.items()},
        pre_HH=_median(bs.pre_HH, mask), pre_HV=_median(bs.pre_HV, mask),
        post_HH=_median(bs.post_HH, mask), post_HV=_median(bs.post_HV, mask),
        agreement=agreement,
        landcover=_LANDCOVER_NAME.get(group, ""),
        hand_m=None, slope_deg=None,
        firms_count=(refs.firms_count(geometry, bs.dates[0], bs.dates[-1])
                     if drop and n <= FIRMS_MAX_AREAS else 0),
        in_fire_perimeter=_in_perimeter(ctx["fire"], geometry),
        cdl_crop=group == "crops",
        min_temp_c=ctx["weather"]["min_temp_c"], rain_mm=ctx["weather"]["rain_mm"],
        frac_significant=float(frac),
        downslope_shape=False,
    )
    cls, label, evidence = classify(stats)
    sensors = {"L": ("HH", "HV"), "C": ("VV", "VH")}.get(agreement, _BANDS)
    effect = max((abs(deltas[b]) for b in sensors if deltas[b] is not None), default=None)
    medians = [_median(p, mask) for p in _p_arrays(bs, agreement)]
    p_value = min((m for m in medians if m is not None), default=1.0)
    return ChangeArea(
        id=f"a{n}",
        geometry=geometry,
        agreement=agreement,
        cls=cls,
        area_ha=float(mask.sum() * bs.grid.res**2 / 10_000.0),
        confidence=_confidence(label, float(frac), effect),
        confidence_label=label,
        p_value=float(p_value),
        change_date=_change_date(bs, mask, agreement, ctx["changed_L"], ctx["changed_C"]),
        evidence=evidence,
        plain_text="",
        series=_series(bs, mask),
    )


# --- plain-language text: cap, timeout, circuit breaker ----------------------------------------


class _Breaker:
    """Wraps an LLM client; after `limit` failures in a row it refuses further calls.

    An exception and an empty reply both count as a failure; a good reply resets the count.
    `explain` turns a refused call into the template text, so the model is simply not asked.
    """

    def __init__(self, client, limit: int = BREAKER_FAILURES):
        self._client, self._limit, self.failures = client, limit, 0
        self.messages = self  # explain() calls client.messages.create(...)

    @property
    def open(self) -> bool:
        return self.failures >= self._limit

    def create(self, **kwargs):
        try:
            reply = self._client.messages.create(**kwargs)
            said = "".join(
                getattr(b, "text", "") for b in reply.content if getattr(b, "type", "text") == "text"
            ).strip()
        except Exception:
            self.failures += 1
            raise
        self.failures = 0 if said else self.failures + 1
        return reply


def _timed(client):
    """The client with a 5 s timeout and no retries (a real SDK client; test doubles pass through)."""
    with_options = getattr(client, "with_options", None)
    if callable(with_options):
        return with_options(timeout=EXPLAIN_TIMEOUT_S, max_retries=0)
    return client


def _default_client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic

        return anthropic.Anthropic(timeout=EXPLAIN_TIMEOUT_S, max_retries=0)
    except Exception as exc:  # noqa: BLE001 - no SDK or bad config: templates
        log.warning("explain: cannot create the LLM client (%s), using templates", type(exc).__name__)
        return None


def explain_areas(areas: list[ChangeArea], client=None) -> None:
    """Set `plain_text` on every area. The LLM words the 10 largest; the rest get the template.

    Each call has a 5 s timeout. After 2 failures in a row the breaker opens and the remaining
    areas get the template without a call. With no client and no API key, all use the template.
    """
    client = client if client is not None else _default_client()
    guard = None if client is None else _Breaker(_timed(client))
    by_size = sorted(areas, key=lambda a: -a.area_ha)
    for rank, area in enumerate(by_size):
        if guard is None or guard.open or rank >= EXPLAIN_MAX_AREAS:
            area.plain_text = explain.template_text(area)
        else:
            area.plain_text = explain.explain(area, guard)


# --- run_box ------------------------------------------------------------------------------------


def _iso(days) -> list[str]:
    return [d.isoformat() for d in days]


def _empty_result(bbox, nisar: dict, publish: PngSink, message: str) -> Result:
    return Result(
        bbox=[float(v) for v in bbox], message=message, nisar=nisar,
        overlays=_blank_overlays(bbox, publish),
    )


def _people(tracts: list[dict], area_list: list[ChangeArea]) -> dict:
    """SVI tracts that overlap a change area, most vulnerable first, without their geometry."""
    if not area_list or not tracts:
        return {"svi_tracts": []}
    changed = unary_union([shape(a.geometry) for a in area_list])
    hit = [t for t in tracts if shape(t["geometry"]).intersects(changed)]
    hit.sort(key=lambda t: -t["rpl_themes"])
    return {"svi_tracts": [{"geoid": t["geoid"], "rpl_themes": t["rpl_themes"], "name": t["name"]}
                           for t in hit]}


def run_box(
    bbox,
    dates=None,
    *,
    read_passes=None,
    progress=None,
    explain_client=None,
    png_sink: PngSink | None = None,
) -> Result:
    """Analyse a lon/lat box (west, south, east, north) and return the `Result`.

    `dates` is (start, end), default the last 12 months. `read_passes(granules, bbox, grid)`
    reads the NISAR granules (default: sequentially, on this machine). `progress(fraction,
    message)` is called with 0.05 to 0.85 by `block_features`, then 0.9 (explaining) and 1.0.
    `explain_client` is an Anthropic-style client for the plain text (default: the SDK client
    when ANTHROPIC_API_KEY is set, else templates). `png_sink(name, png_bytes) -> url` stores the
    five overlay images (names change, l, c, before, after); by default they are data URLs.

    Raises `NoUsablePasses` when no calibrated NISAR stack covers the box. A box that is mostly
    fill, or too small to test, returns a normal Result with no areas and a message.
    """
    publish = png_sink or _data_url
    seen: list = []  # granules handed to the reader: the series, if the test cannot run
    reader = read_passes or features._read_sequential

    def capture(granules, box, grid):
        seen.extend(granules)
        return reader(granules, box, grid)

    try:
        bs = features.block_features(bbox, dates, read_passes=capture, progress=progress)
    except (detect.TooFewBlocks, detect.NoStableBlocks) as exc:
        log.warning("box has too few usable blocks: %s", exc)
        first = seen[0]
        nisar = {"track": first.track, "direction": first.direction,
                 "dates": _iso(sorted({g.start.date() for g in seen}))}
        return _empty_result(bbox, nisar, publish, NO_VALID_MESSAGE)

    nisar = {"track": bs.stack.track, "direction": bs.stack.direction, "dates": _iso(bs.stack.dates)}
    if float(bs.valid.mean()) < MIN_VALID_FRACTION:
        return _empty_result(bbox, nisar, publish, NO_VALID_MESSAGE)

    changed_L = detect.changed(bs.p_L, [bs.rel_dHH, bs.rel_dHV], Q, MIN_DB)
    changed_C = detect.changed(bs.p_C, [bs.rel_dVV, bs.rel_dVH], Q, MIN_DB)
    found = areas_mod.label_areas(changed_L, changed_C, bs.grid, MIN_HA)
    ctx = {
        "sig_L": detect.bh_fdr(bs.p_L, Q), "sig_C": detect.bh_fdr(bs.p_C, Q),
        "changed_L": changed_L, "changed_C": changed_C,
        "weather": _weather(bs, bbox) if found else {"min_temp_c": None, "rain_mm": None},
        "fire": _fire_geometry(refs.nifc_perimeters(bbox, bs.dates[-1].year)) if found else None,
    }
    area_list = [
        _build_area(n, geometry, mask, agreement, bs, ctx)
        for n, (geometry, mask, agreement) in enumerate(found, start=1)
    ]
    if progress:
        progress(0.9, "Writing plain-language explanations")
    explain_areas(area_list, explain_client)

    result = Result(
        bbox=[float(v) for v in bbox],
        message=None if bs.s1 is not None else NO_S1_MESSAGE,
        nisar=nisar,
        s1=None if bs.s1 is None else {"track": bs.s1["track"], "dates": _iso(bs.s1["dates"])},
        overlays=_overlays(bs, [(m, a) for _, m, a in found], publish),
        areas=area_list,
        people=_people(refs.svi_tracts(bbox) if found else [], area_list),
    )
    if progress:
        progress(1.0, "Done")
    return result

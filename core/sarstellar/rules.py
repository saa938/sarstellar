"""Cause rules: turn a change area's measured numbers into a labelled cause plus its evidence.

The rules follow the table in `docs/research/science.md` and the C-only rules in the design spec
section 6. Each threshold is tagged where it is defined; the tag is the provenance shown to the
user in the "Rule fired" evidence:

    ATBD       a NISAR ATBD sample threshold used as written (prelaunch, single-site): only the
               open-water HH x HV product and the flooded-vegetation post-level cues. The
               disturbance ATBD is a CUSUM on the HV series, so two-date HV limits are NOT ATBD.
    research   from the science.md rule table (literature values)
    judgment   the builder's call, to be tuned on the scorecard's calibration split

`classify` never raises on missing numbers: a rule that needs one does not fire and the area falls
through to `uncertain`. Missing information can lower confidence but never raise it. The
"freeze-up" false positive is suppressed, never emitted: it comes back as `uncertain` with a
"possible freeze" evidence note.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .types import Evidence

# The twelve class strings of the Result contract. Freeze-up is suppressed and never emitted.
CLASSES = (
    "forest_loss", "burn", "flood_open_water", "flooded_vegetation", "crop_cycle", "harvest",
    "low_veg_loss", "soil_wetting", "construction", "landslide", "wet_snow", "uncertain",
)  # fmt: skip

# ---- thresholds (dB are relative changes, after minus before, on whole-area medians) ----------
WATER_PRODUCT_MAX = 5e-5  # ATBD: open water when post HH * HV (linear) is below this
WATER_DHH_MAX = -6.0  # judgment: and HH fell by at least this much
FLOODVEG_DHH_MIN = 3.0  # judgment: HH rose by at least this much
FLOODVEG_DHV_ABS_MAX = 2.0  # research: |dHV| at most this (HV flat)
FLOODVEG_POST_HH_DB = -3.0  # ATBD: post HH above 0.5 linear (-3 dB) ...
FLOODVEG_POST_RATIO_DB = 9.0  # ATBD: ... or post HH/HV above 8 linear (9 dB)
HAND_MAX_M = 15.0  # judgment: flood water needs low ground (height above nearest drainage)
FIRE_DHV_MAX = -2.0  # research: burn HV drop
FIRE_DHH_MAX = 0.0  # research: burn HH does not rise
CLEARCUT_DHV_MAX = -3.0  # research: clear-cut HV drop (3-5 tropics, 2-3 boreal; CONUS uses 3)
CROP_DHV_ABS_MIN = 2.0  # judgment: with a CDL crop mask, an HV swing this big is the crop cycle
WETTING_MIN_DB, WETTING_MAX_DB = 1.0, 4.0  # research: soil wetting is +1 to +4 dB in HH and HV
WET_RATIO_MAX_DB = 1.0  # judgment: |dHH - dHV| under this (the HH/HV ratio stays flat)
WET_RAIN_MIN_MM = 1.0  # judgment: needs some rain (the table says check IMERG)
CONSTRUCTION_DHH_MIN = 5.0  # judgment: HH jumps by at least this much
LANDSLIDE_SLOPE_MIN_DEG = 15.0  # research: slope above this plus a downslope shape
LANDSLIDE_DHV_MAX = -3.0  # judgment: HV drop
SNOW_DROP_DB = -2.0  # judgment: HH and HV each fall by at least this much ...
SNOW_TEMP_RANGE_C = (0.0, 3.0)  # judgment: ... with a minimum temperature in this melt range
FREEZE_TEMP_C = 0.0  # research: suppress down/down when the minimum temperature is below this
FREEZE_DHH_MAX = -1.0  # judgment: "both bands down" means co-pol at most this ...
FREEZE_DHV_MAX = -2.0  # judgment: ... and cross-pol at most this (also used for VV / VH)
C_VH_DROP_DB = -2.0  # judgment (design spec): C-only VH drop of at least 2 dB in low vegetation
C_RISE_MIN_DB = 2.0  # judgment: C-only VV or VH rise of at least this much
FLAT_SLOPE_MAX_DEG = 5.0  # judgment: "flat ground" for the C-only wetting rule

_ATBD = "NISAR ATBD sample threshold (prelaunch, single-site)"
_RESEARCH = "research table (docs/research/science.md, literature values)"
_JUDGMENT = "builder judgment, tune on the scorecard"
_SPEC = "builder judgment (design spec C-band rule)"
_LOW_CAP = ("landslide", "wet_snow", "uncertain")  # classes that are never above Low confidence

_BAND_SENSOR = {"HH": "NISAR L-band", "HV": "NISAR L-band"}
_BAND_SENSOR |= {"VV": "Sentinel-1 C-band", "VH": "Sentinel-1 C-band"}


@dataclass
class AreaStats:
    """Aggregate numbers for one change area. Changes are median relative dB (after - before)."""

    dHH: float | None = None
    dHV: float | None = None
    dVV: float | None = None
    dVH: float | None = None
    ci: dict[str, Any] = field(default_factory=dict)  # band ("HH".."VH") -> (lo, hi) or None
    pre_HH: float | None = None  # level before, dB
    pre_HV: float | None = None
    post_HH: float | None = None  # level after, dB
    post_HV: float | None = None
    agreement: str = "both"  # "L", "C" or "both"
    landcover: str = ""  # NLCD class name, "" when unknown
    hand_m: float | None = None
    slope_deg: float | None = None
    firms_count: int | None = 0  # None (FIRMS lookup failed) counts as no detections
    in_fire_perimeter: bool = False
    cdl_crop: bool = False
    min_temp_c: float | None = None
    rain_mm: float | None = None
    frac_significant: float | None = None  # share of blocks passing the FDR test; None gives Low
    downslope_shape: bool | None = None  # elongated down the slope (caller measures); None: no


@dataclass
class _Hit:
    cls: str
    rule: str  # the rule that fired, in words
    source: str  # where its thresholds come from
    delta: float | None  # the dB change that drives the confidence label
    evidence: list[Evidence] = field(default_factory=list)  # context beyond the band changes
    suppressed: bool = False  # a suppressed false positive: the learned model may not override
    cap_medium: bool = False  # look-alike risk: confidence is at most Medium


def _v(x: Any) -> float | None:
    """A finite float, or None for None/NaN/inf (missing numbers never reach a comparison)."""
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _ge(x: float | None, t: float) -> bool:
    return x is not None and x >= t


def _le(x: float | None, t: float) -> bool:
    return x is not None and x <= t


_LANDCOVER_KEYS = (  # first match wins, matched against the lower-cased NLCD class name
    ("forest", ("forest", "woody")),
    ("developed", ("developed", "urban")),
    ("water", ("water",)),
    ("lowveg", ("grass", "shrub", "scrub", "herbaceous", "pasture", "hay", "crop")),
    ("barren", ("barren",)),
)


def _landcover_group(landcover: str) -> str:
    """Coarse NLCD group: forest, developed, water, lowveg, barren, other or unknown ("")."""
    t = (landcover or "").lower()
    if not t:
        return "unknown"
    return next((g for g, keys in _LANDCOVER_KEYS if any(k in t for k in keys)), "other")


def confidence_label(frac_significant: float | None, median_delta_db: float | None) -> str:
    """High: 80% or more of the area's blocks significant and |median change| at least 3 dB.
    Medium: at least 50% significant. Otherwise Low."""
    frac = _v(frac_significant) or 0.0
    delta = abs(_v(median_delta_db) or 0.0)
    if frac >= 0.8 and delta >= 3.0:
        return "High"
    if frac >= 0.5:
        return "Medium"
    return "Low"


def _ci(s: AreaStats, band: str) -> list[float] | None:
    try:  # a missing or malformed interval is simply left out
        lo, hi = (round(float(x), 2) for x in (s.ci.get(band) or s.ci.get("d" + band)))
    except (TypeError, ValueError):
        return None
    return [lo, hi] if math.isfinite(lo) and math.isfinite(hi) else None


def _delta(s: AreaStats, band: str) -> float | None:
    return _v(getattr(s, "d" + band))


def _band_evidence(s: AreaStats, first: tuple[str, ...]) -> list[Evidence]:
    order = list(first) + [b for b in ("HH", "HV", "VV", "VH") if b not in first]
    return [
        Evidence(f"{b} change", round(d, 2), _ci(s, b), "dB", _BAND_SENSOR[b])
        for b in order
        if (d := _delta(s, b)) is not None
    ]


def _ev(label: str, value: float | str, unit: str = "", note: str = "") -> Evidence:
    """A context evidence entry with no interval (band changes build theirs with a CI)."""
    return Evidence(label, value, None, unit, note)


def _landcover_evidence(s: AreaStats) -> list[Evidence]:
    return [_ev("Land cover", s.landcover, note="NLCD")] if s.landcover else []


_CROPLAND = _ev("Cropland mask", "crop", note="USDA Cropland Data Layer")


def _firms(s: AreaStats) -> int:
    """FIRMS detection count; None, NaN or a negative number all mean no detections."""
    n = _v(s.firms_count)
    return int(n) if n is not None and n > 0 else 0


def _fire(s: AreaStats) -> bool:
    return _firms(s) > 0 or bool(s.in_fire_perimeter)


def _has_crop(s: AreaStats) -> bool:
    return bool(s.cdl_crop)


def _fire_evidence(s: AreaStats) -> list[Evidence]:
    return [
        _ev("FIRMS detections", _firms(s), "count", "NASA FIRMS hotspots"),
        _ev("Inside fire perimeter", "yes" if s.in_fire_perimeter else "no", "", "NIFC perimeters"),
    ]


def _hand_ok(s: AreaStats) -> bool:
    hand = _v(s.hand_m)
    return hand is None or hand <= HAND_MAX_M


def _hand_evidence(s: AreaStats) -> list[Evidence]:
    hand = _v(s.hand_m)
    return (
        [] if hand is None else [_ev("HAND", round(hand, 1), "m", "height above nearest drainage")]
    )


def _post_product(s: AreaStats) -> float | None:
    hh, hv = _v(s.post_HH), _v(s.post_HV)
    return None if hh is None or hv is None else 10 ** (hh / 10.0) * 10 ** (hv / 10.0)


def _flood_context_ok(s: AreaStats, group: str) -> bool:
    """Where flooded vegetation is plausible: low ground, not built-up, and (when the levels
    after are known) the ATBD cue: HH above -3 dB or HH/HV above 9 dB."""
    hh, hv = _v(s.post_HH), _v(s.post_HV)
    bright = (
        hh is None or hv is None or hh > FLOODVEG_POST_HH_DB or (hh - hv) > FLOODVEG_POST_RATIO_DB
    )
    return _hand_ok(s) and group != "developed" and bright


def _flooded_veg_risky(s: AreaStats) -> bool:
    """Rice paddies and new construction look like flooded vegetation in HH/HV. A crop mask, or
    no HAND value to confirm low ground, means the label can be at most Medium confidence."""
    return bool(s.cdl_crop) or _v(s.hand_m) is None


def _frozen(s: AreaStats) -> bool:
    t = _v(s.min_temp_c)
    return t is not None and t < FREEZE_TEMP_C


def _freeze_hit(s: AreaStats, cross: float | None, sensor: str) -> _Hit:
    """The suppressed freeze-up false positive: reported as uncertain, with a note saying why."""
    temp = round(_v(s.min_temp_c), 1)
    note = (
        f"possible freeze: {sensor} co- and cross-pol both fell while the minimum temperature "
        f"was {temp:.1f} C (below 0 C); suppressed as a likely freeze-up false positive"
    )
    rule = "Freeze-up suppressed: both bands fell on a below-freezing day"
    # the 0 C limit is from the research table; the band drops, and applying it to C-band, are ours
    source = (
        f"{_RESEARCH} for the 0 C limit; band drops are {_JUDGMENT}"
        if sensor == "NISAR"
        else f"{_JUDGMENT} (the 0 C limit is from the research table, applied here to C-band)"
    )
    return _Hit(
        "uncertain", rule, source, cross, [_ev("Minimum temperature", temp, "C", note)], True
    )


def _uncertain(rule: str, note: str) -> _Hit:
    return _Hit("uncertain", rule, "no rule matched", None, [_ev("Cause", "uncertain", note=note)])


def _classify_l(s: AreaStats) -> _Hit:
    """Rules for areas NISAR saw (agreement L or both): HH and HV changes drive the label."""
    hh, hv = _delta(s, "HH"), _delta(s, "HV")
    group = _landcover_group(s.landcover)
    if hh is None and hv is None:
        return _uncertain("No L-band change numbers", "no NISAR HH/HV change was available")

    # 1. open water: very dark after, and HH dropped hard, on low ground. Land cover that is
    #    already permanent open water is not a new flood (wind and calm days change a lake's return)
    product = _post_product(s)
    dark_after = product is not None and product < WATER_PRODUCT_MAX
    water_signature = dark_after and _le(hh, WATER_DHH_MAX) and _hand_ok(s)
    if water_signature and group != "water":
        rule = "After the change HH x HV is below 5e-5 (linear) and HH fell by 6 dB or more"
        source = f"{_ATBD} for the 5e-5 product; the 6 dB HH drop and HAND limit are {_JUDGMENT}"
        level = _ev("HH x HV after (linear)", float(f"{product:.3g}"), "linear", "ATBD limit 5e-5")
        return _Hit("flood_open_water", rule, source, hh, [level, *_hand_evidence(s)])

    # 2. burn: down/down, but only called "fire" with FIRMS or a perimeter
    if _fire(s) and _le(hv, FIRE_DHV_MAX) and _le(hh, FIRE_DHH_MAX):
        rule = "HV fell 2 dB or more, HH did not rise, fire evidence (FIRMS or perimeter) present"
        return _Hit("burn", rule, _RESEARCH, hv, _fire_evidence(s))

    # 3. freeze-up false positive: both bands down on a below-freezing day
    if _frozen(s) and _le(hh, FREEZE_DHH_MAX) and _le(hv, FREEZE_DHV_MAX):
        return _freeze_hit(s, hv, "NISAR")

    # 4. flooded vegetation: HH up, HV about flat, near water-prone ground, not built-up
    flat_hv = hv is not None and abs(hv) <= FLOODVEG_DHV_ABS_MAX
    if _ge(hh, FLOODVEG_DHH_MIN) and flat_hv and _flood_context_ok(s, group):
        post = [
            _ev(f"{b} after", round(p, 1), "dB", "level after the change")
            for b, p in (("HH", _v(s.post_HH)), ("HV", _v(s.post_HV)))
            if p is not None
        ]
        rule = "HH rose 3 dB or more, HV stayed within 2 dB (possible double-bounce response)"
        source = (
            f"{_ATBD} for the post-level cue (when levels are known); {_RESEARCH} for flat HV; "
            f"the 3 dB HH rise is {_JUDGMENT}"
        )
        # Rice paddies and new construction look the same in HH/HV. Without a HAND value that
        # confirms low ground, or with a crop mask, the label is only ever Medium confidence.
        risky = _flooded_veg_risky(s)
        note = "could also be rice paddy or new construction"
        look_alikes = [_ev("Look-alikes", "rice paddy or new construction", note=note)]
        evidence = [*post, *_hand_evidence(s), *(look_alikes if risky else [])]
        return _Hit("flooded_vegetation", rule, source, hh, evidence, cap_medium=risky)

    # 5. soil wetting: both bands up 1-4 dB together, with rain
    rain = _v(s.rain_mm)
    rose = [x is not None and WETTING_MIN_DB <= x <= WETTING_MAX_DB for x in (hh, hv)]
    if all(rose) and abs(hh - hv) < WET_RATIO_MAX_DB and _ge(rain, WET_RAIN_MIN_MM):
        rule = "HH and HV both rose 1-4 dB together (flat ratio) after rain"
        source = f"{_RESEARCH} for 1-4 dB; the flat-ratio limit and rain minimum are {_JUDGMENT}"
        rain_ev = _ev("Rain", round(rain, 1), "mm", "Open-Meteo archive at the pass date")
        return _Hit("soil_wetting", rule, source, max(hh, hv), [rain_ev])

    # 6. construction: a large HH jump (persistence needs a longer series than two dates)
    if _ge(hh, CONSTRUCTION_DHH_MIN) and group != "water":
        rule = "HH jumped 5 dB or more (consistent with new hard surfaces or structures)"
        persistence = _ev("Persistence", "not checked", note="needs more than two dates")
        return _Hit("construction", rule, _JUDGMENT, hh, [persistence])

    # 7. crop cycle: with a crop mask, a big HV swing is farming, not disturbance
    if s.cdl_crop and hv is not None and abs(hv) >= CROP_DHV_ABS_MIN:
        rule = "HV swung 2 dB or more on land the Cropland Data Layer marks as crop"
        return _Hit("crop_cycle", rule, _JUDGMENT, hv, [_CROPLAND])

    # 8. landslide: HV drop on a steep slope in a downslope shape (always low confidence)
    slope = _v(s.slope_deg)
    steep = slope is not None and slope > LANDSLIDE_SLOPE_MIN_DEG
    if s.downslope_shape is True and steep and _le(hv, LANDSLIDE_DHV_MAX):
        rule = "HV fell 3 dB or more on a slope over 15 degrees in a downslope shape"
        source = f"{_RESEARCH} for the 15 degree slope; the 3 dB HV drop is {_JUDGMENT}; always Low"
        return _Hit(
            "landslide", rule, source, hv, [_ev("Slope", round(slope, 1), "deg", "terrain")]
        )

    # 9. wet snow: both bands down near the melting point (low confidence only)
    t = _v(s.min_temp_c)
    melting = t is not None and SNOW_TEMP_RANGE_C[0] <= t <= SNOW_TEMP_RANGE_C[1]
    if _le(hh, SNOW_DROP_DB) and _le(hv, SNOW_DROP_DB) and melting:
        rule = "HH and HV both fell 2 dB or more with a minimum temperature of 0-3 C"
        source = _JUDGMENT + "; C-band is the better snow sensor"
        cold = _ev("Minimum temperature", round(t, 1), "C", "near the melting point")
        return _Hit("wet_snow", rule, source, min(hh, hv), [cold])

    # 10. vegetation loss: HV drop. Forest or unknown cover reads as clear-cut, low cover as grass loss
    if _le(hv, CLEARCUT_DHV_MAX):
        lc = _landcover_evidence(s)
        if group in ("forest", "unknown"):
            rule = "HV fell 3 dB or more (consistent with canopy loss)"
            return _Hit("forest_loss", rule, _RESEARCH, hv, lc)
        if group == "lowveg":
            # the research table's HV drop is for forest; using it on low vegetation is ours
            rule = "HV fell 3 dB or more over low vegetation"
            source = f"{_JUDGMENT} (extends the research table's forest HV drop to low vegetation)"
            return _Hit("low_veg_loss", rule, source, hv, lc)

    if water_signature:  # dark, big HH drop, but the land cover is already open water
        return _uncertain(
            "Dark return on land already mapped as open water",
            "permanent open water (NLCD): a darker return is not new flooding",
        )
    return _uncertain("No cause rule matched", "the L-band changes fit no cause rule")


def _classify_c(s: AreaStats) -> _Hit:
    """Rules for Sentinel-1-majority areas: VV and VH changes drive the label."""
    vv, vh = _delta(s, "VV"), _delta(s, "VH")
    group = _landcover_group(s.landcover)
    low_veg = group == "lowveg" or s.cdl_crop
    vh_drop_in_low_veg = _le(vh, C_VH_DROP_DB) and low_veg
    rule = "Sentinel-1 majority: VH fell 2 dB or more in low vegetation"

    # same order as the L-band path: independent fire evidence first, then freeze suppression
    if vh_drop_in_low_veg and _fire(s):
        return _Hit("burn", rule + ", with fire evidence", _SPEC, vh, _fire_evidence(s))

    if _frozen(s) and _le(vv, FREEZE_DHH_MAX) and _le(vh, FREEZE_DHV_MAX):
        return _freeze_hit(s, vh, "Sentinel-1")

    if vh_drop_in_low_veg:
        if s.cdl_crop:
            return _Hit("harvest", rule + " on a Cropland Data Layer crop", _SPEC, vh, [_CROPLAND])
        return _Hit("low_veg_loss", rule, _SPEC, vh, _landcover_evidence(s))

    slope = _v(s.slope_deg)
    flat_low = (
        _v(s.hand_m) is not None and _hand_ok(s) and (slope is None or slope <= FLAT_SLOPE_MAX_DEG)
    )
    if (_ge(vv, C_RISE_MIN_DB) or _ge(vh, C_RISE_MIN_DB)) and flat_low:
        rise = max(d for d in (vv, vh) if d is not None)
        rule = "Sentinel-1 majority: VV or VH rose 2 dB or more over flat, low-HAND ground"
        what = "possible surface water or wetting"
        return _Hit(
            "soil_wetting", rule, _SPEC, rise, [_ev("Cause", what, note=what), *_hand_evidence(s)]
        )

    return _uncertain(
        "Sentinel-1 majority; no C-band cause rule matched",
        "Changed, cause uncertain: Sentinel-1-majority area",
    )


def _nan_if_missing(x: Any) -> float:
    v = _v(x)
    return float("nan") if v is None else v


def _feature_row(s: AreaStats) -> dict[str, Any]:
    """One row of the numbers the learned model sees (missing values are NaN)."""
    numeric = ("dHH", "dHV", "dVV", "dVH", "pre_HH", "pre_HV", "post_HH", "post_HV")
    row = {k: _nan_if_missing(getattr(s, k)) for k in (*numeric, "hand_m", "slope_deg")}
    return {
        **row,
        "landcover": s.landcover,
        "firms_count": _firms(s),
        "agreement": s.agreement,
    }


# Evidence a class needs whoever proposes it, the rules or the learned model: "burn" only with
# FIRMS or a perimeter, "harvest" and "crop_cycle" only with a Cropland Data Layer crop.
_EVIDENCE_GATES = {"burn": _fire, "harvest": _has_crop, "crop_cycle": _has_crop}


def _apply_model(s: AreaStats, hit: _Hit, model: Any) -> _Hit:
    """Let the learned model relabel the area, but only for classes where it beat the rules.

    `model` needs `.winners` (classes where the model's held-out F1 beat the rules) and
    `.predict(DataFrame) -> array of class names`. The model has no way around the evidence
    gates: a predicted class whose gate fails keeps the rules' label. Anything missing or
    failing also keeps the rules.
    """
    winners = getattr(model, "winners", None)
    if not winners or hit.suppressed:
        return hit
    try:
        import pandas as pd

        pred = str(model.predict(pd.DataFrame([_feature_row(s)]))[0])
    except Exception:  # noqa: BLE001 - a broken or missing model must never break a result
        return hit
    if pred == hit.cls or pred not in winners or pred not in CLASSES:
        return hit
    gate = _EVIDENCE_GATES.get(pred)
    if gate is not None and not gate(s):
        return hit
    deltas = [abs(d) for d in (_delta(s, b) for b in ("HH", "HV", "VV", "VH")) if d is not None]
    note = f"rules alone said {hit.cls}; the learned model beat the rules on held-out states for {pred}"
    return _Hit(
        pred,
        "Learned model (held-out winner for this class)",
        "learned cause model",
        max(deltas) if deltas else None,
        [_ev("Learned model", pred, note=note)],
        cap_medium=pred == "flooded_vegetation" and _flooded_veg_risky(s),
    )


def classify(stats: AreaStats, model: Any = None) -> tuple[str, str, list[Evidence]]:
    """Label one change area: returns (class, confidence label, evidence).

    Areas only Sentinel-1 saw use the C-band rules; every other area uses the L-band rules.
    `model` is an optional learned `CauseModel`, used only for classes in its `winners`.
    """
    hit = _classify_c(stats) if stats.agreement == "C" else _classify_l(stats)
    if model is not None:
        hit = _apply_model(stats, hit, model)
    first = ("VV", "VH") if stats.agreement == "C" else ("HH", "HV")
    evidence = (
        [Evidence("Rule fired", hit.rule, None, "", hit.source)]
        + _band_evidence(stats, first)
        + hit.evidence
    )
    label = "Low" if hit.cls in _LOW_CAP else confidence_label(stats.frac_significant, hit.delta)
    if hit.cap_medium and label == "High":
        label = "Medium"
    return hit.cls, label, evidence

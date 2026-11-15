"""Cause rules: turn a change area's measured numbers into a labelled cause plus its evidence.

The rules follow the table in `docs/research/science.md` (physics of L-band HH/HV) and the
C-only rules in the design spec section 6. Each threshold is tagged where it is defined:

    ATBD       taken from a NISAR ATBD or the research table (prelaunch, single-site values)
    judgment   the builder's call, to be tuned on the scorecard's calibration split

`classify` never raises on missing numbers: a rule that needs a number it does not have simply
does not fire, and the area falls through to `uncertain`. The "freeze-up" false positive is
suppressed, never emitted: it comes back as `uncertain` with a "possible freeze" evidence note.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .types import Evidence

CLASSES = (
    "forest_loss",
    "burn",
    "flood_open_water",
    "flooded_vegetation",
    "crop_cycle",
    "harvest",
    "low_veg_loss",
    "soil_wetting",
    "construction",
    "landslide",
    "wet_snow",
    "uncertain",
)

# ---- thresholds (dB are relative changes, after minus before, on whole-area medians) ----------
WATER_PRODUCT_MAX = 5e-5  # ATBD: open water when post HH * HV (linear) is below this
WATER_DHH_MAX = -6.0  # judgment: and HH fell by at least this much
FLOODVEG_DHH_MIN = 3.0  # judgment: HH rose by at least this much
FLOODVEG_DHV_ABS_MAX = 2.0  # table: |dHV| at most this (HV flat)
FLOODVEG_POST_HH_DB = -3.0  # ATBD: post HH above 0.5 linear (-3 dB) ...
FLOODVEG_POST_RATIO_DB = 9.0  # ATBD: ... or post HH/HV above 8 linear (9 dB)
HAND_MAX_M = 15.0  # judgment: flood water needs low ground (height above nearest drainage)
FIRE_DHV_MAX = -2.0  # table: burn HV drop
FIRE_DHH_MAX = 0.0  # table: burn HH does not rise
CLEARCUT_DHV_MAX = -3.0  # table: clear-cut HV drop (3-5 tropics, 2-3 boreal; CONUS uses 3)
CROP_DHV_ABS_MIN = 2.0  # judgment: with a CDL crop mask, an HV swing this big is the crop cycle
WETTING_MIN_DB, WETTING_MAX_DB = 1.0, 4.0  # table: soil wetting is +1 to +4 dB in HH and HV
WETTING_RATIO_MAX_DB = 1.0  # judgment: |dHH - dHV| under this (the HH/HV ratio stays flat)
WETTING_RAIN_MIN_MM = 1.0  # judgment: needs some rain (the table says check IMERG)
CONSTRUCTION_DHH_MIN = 5.0  # judgment: HH jumps by at least this much
LANDSLIDE_SLOPE_MIN_DEG = 15.0  # table: slope above this plus a downslope shape
LANDSLIDE_DHV_MAX = -3.0  # judgment: HV drop
SNOW_DROP_DB = -2.0  # judgment: HH and HV each fall by at least this much ...
SNOW_TEMP_RANGE_C = (0.0, 3.0)  # judgment: ... with a minimum temperature in this melt range
FREEZE_TEMP_C = 0.0  # table: suppress down/down when the minimum temperature is below this
FREEZE_DHH_MAX = -1.0  # judgment: "both bands down" means HH at most this ...
FREEZE_DHV_MAX = -2.0  # ... and HV at most this
C_VH_DROP_DB = -2.0  # spec: C-only VH drop of at least 2 dB in low vegetation
C_RISE_MIN_DB = 2.0  # judgment: C-only VV or VH rise of at least this much
FLAT_SLOPE_MAX_DEG = 5.0  # judgment: "flat ground" for the C-only wetting rule

_ATBD = "NISAR ATBD / research table (prelaunch value)"
_JUDGMENT = "builder judgment, tune on the scorecard"
_SPEC = "design spec C-band rule (builder judgment)"
_LOW_CAP = ("landslide", "wet_snow", "uncertain")  # classes that are never above Low confidence

_L_BANDS = ("HH", "HV")
_BAND_SENSOR = {
    "HH": "NISAR L-band",
    "HV": "NISAR L-band",
    "VV": "Sentinel-1 C-band",
    "VH": "Sentinel-1 C-band",
}


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
    firms_count: int = 0
    in_fire_perimeter: bool = False
    cdl_crop: bool = False
    min_temp_c: float | None = None
    rain_mm: float | None = None
    frac_significant: float = 1.0  # share of the area's blocks that passed the FDR test
    downslope_shape: bool = False  # the area is elongated down the slope (caller measures it)


@dataclass
class _Hit:
    cls: str
    rule: str  # the rule that fired, in words
    source: str  # where its thresholds come from
    delta: float | None  # the dB change that drives the confidence label
    evidence: list[Evidence] = field(default_factory=list)  # context beyond the band changes
    suppressed: bool = False  # a suppressed false positive: the learned model may not override


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


def _sig(x: float) -> float:
    return float(f"{x:.3g}")


def _landcover_group(landcover: str) -> str:
    """Coarse NLCD group: forest, lowveg, developed, water, barren, other or unknown."""
    t = (landcover or "").lower()
    if not t:
        return "unknown"
    if "forest" in t or "woody" in t:
        return "forest"
    if "developed" in t or "urban" in t:
        return "developed"
    if "water" in t:
        return "water"
    if any(k in t for k in ("grass", "shrub", "scrub", "herbaceous", "pasture", "hay", "crop")):
        return "lowveg"
    if "barren" in t:
        return "barren"
    return "other"


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
    ci = s.ci.get(band) if s.ci.get(band) is not None else s.ci.get("d" + band)
    if ci is None:
        return None
    try:
        lo, hi = (float(x) for x in ci)
    except (TypeError, ValueError):
        return None
    return [round(lo, 2), round(hi, 2)] if math.isfinite(lo) and math.isfinite(hi) else None


def _delta(s: AreaStats, band: str) -> float | None:
    return _v(getattr(s, "d" + band))


def _band_evidence(s: AreaStats, first: tuple[str, ...]) -> list[Evidence]:
    order = list(first) + [b for b in ("HH", "HV", "VV", "VH") if b not in first]
    return [
        Evidence(f"{b} change", round(d, 2), _ci(s, b), "dB", _BAND_SENSOR[b])
        for b in order
        if (d := _delta(s, b)) is not None
    ]


def _fire(s: AreaStats) -> bool:
    return s.firms_count > 0 or s.in_fire_perimeter


def _fire_evidence(s: AreaStats) -> list[Evidence]:
    return [
        Evidence("FIRMS detections", int(s.firms_count), None, "count", "NASA FIRMS hotspots"),
        Evidence(
            "Inside fire perimeter",
            "yes" if s.in_fire_perimeter else "no",
            None,
            "",
            "NIFC 2026 perimeters",
        ),
    ]


def _hand_ok(s: AreaStats) -> bool:
    hand = _v(s.hand_m)
    return hand is None or hand <= HAND_MAX_M


def _hand_evidence(s: AreaStats) -> list[Evidence]:
    hand = _v(s.hand_m)
    if hand is None:
        return []
    return [Evidence("HAND", round(hand, 1), None, "m", "height above nearest drainage")]


def _post_product(s: AreaStats) -> float | None:
    hh, hv = _v(s.post_HH), _v(s.post_HV)
    if hh is None or hv is None:
        return None
    return 10 ** (hh / 10.0) * 10 ** (hv / 10.0)


def _post_ok_for_flooded_veg(s: AreaStats) -> bool:
    """ATBD cue: HH after above -3 dB or HH/HV after above 9 dB. Skipped when levels are unknown."""
    hh, hv = _v(s.post_HH), _v(s.post_HV)
    if hh is None or hv is None:
        return True
    return hh > FLOODVEG_POST_HH_DB or (hh - hv) > FLOODVEG_POST_RATIO_DB


def _frozen(s: AreaStats) -> bool:
    t = _v(s.min_temp_c)
    return t is not None and t < FREEZE_TEMP_C


def _freeze_hit(s: AreaStats, co: float | None, cross: float | None, sensor: str) -> _Hit:
    note = (
        f"possible freeze: {sensor} co- and cross-pol both fell while the minimum temperature "
        f"was {_v(s.min_temp_c):.1f} C (below 0 C); suppressed as a likely freeze-up false positive"
    )
    return _Hit(
        "uncertain",
        "Freeze-up suppressed: both bands fell on a below-freezing day",
        _ATBD + "; band thresholds are judgment",
        cross,
        [Evidence("Minimum temperature", round(_v(s.min_temp_c), 1), None, "C", note)],
        suppressed=True,
    )


def _uncertain(rule: str, note: str) -> _Hit:
    return _Hit(
        "uncertain", rule, "no rule matched", None, [Evidence("Cause", "uncertain", None, "", note)]
    )


def _classify_l(s: AreaStats) -> _Hit:
    """Rules for areas NISAR saw (agreement L or both): HH and HV changes drive the label."""
    hh, hv = _delta(s, "HH"), _delta(s, "HV")
    group = _landcover_group(s.landcover)
    if hh is None and hv is None:
        return _uncertain("No L-band change numbers", "no NISAR HH/HV change was available")

    # 1. open water: very dark after, and HH dropped hard, on low ground
    product = _post_product(s)
    if (
        product is not None
        and product < WATER_PRODUCT_MAX
        and _le(hh, WATER_DHH_MAX)
        and _hand_ok(s)
    ):
        return _Hit(
            "flood_open_water",
            "After the change HH x HV is below 5e-5 (linear) and HH fell by 6 dB or more",
            _ATBD + "; the 6 dB HH drop and HAND limit are judgment",
            hh,
            [
                Evidence(
                    "HH x HV after (linear)",
                    _sig(product),
                    None,
                    "linear",
                    "NISAR inundation ATBD open-water value is 5e-5",
                )
            ]
            + _hand_evidence(s),
        )

    # 2. burn: down/down, but only called "fire" with FIRMS or a perimeter
    if _fire(s) and _le(hv, FIRE_DHV_MAX) and _le(hh, FIRE_DHH_MAX):
        return _Hit(
            "burn",
            "HV fell 2 dB or more, HH did not rise, and fire evidence (FIRMS or perimeter) is present",
            _ATBD,
            hv,
            _fire_evidence(s),
        )

    # 3. freeze-up false positive: both bands down on a below-freezing day
    if _frozen(s) and _le(hh, FREEZE_DHH_MAX) and _le(hv, FREEZE_DHV_MAX):
        return _freeze_hit(s, hh, hv, "NISAR")

    # 4. flooded vegetation: HH up, HV about flat, near water-prone ground, not built-up
    if (
        _ge(hh, FLOODVEG_DHH_MIN)
        and hv is not None
        and abs(hv) <= FLOODVEG_DHV_ABS_MAX
        and _hand_ok(s)
        and group != "developed"
        and _post_ok_for_flooded_veg(s)
    ):
        post = [
            Evidence(f"{b} after", round(p, 1), None, "dB", "level after the change")
            for b, p in (("HH", _v(s.post_HH)), ("HV", _v(s.post_HV)))
            if p is not None
        ]
        return _Hit(
            "flooded_vegetation",
            "HH rose 3 dB or more while HV stayed within 2 dB (double-bounce off standing water)",
            _ATBD + "; the 3 dB HH rise is judgment",
            hh,
            post + _hand_evidence(s),
        )

    # 5. soil wetting: both bands up 1-4 dB together, with rain
    rain = _v(s.rain_mm)
    if (
        hh is not None
        and hv is not None
        and WETTING_MIN_DB <= hh <= WETTING_MAX_DB
        and WETTING_MIN_DB <= hv <= WETTING_MAX_DB
        and abs(hh - hv) < WETTING_RATIO_MAX_DB
        and rain is not None
        and rain >= WETTING_RAIN_MIN_MM
    ):
        return _Hit(
            "soil_wetting",
            "HH and HV both rose 1-4 dB together (flat ratio) after rain",
            _ATBD + "; the flat-ratio limit and rain minimum are judgment",
            max(hh, hv),
            [Evidence("Rain", round(rain, 1), None, "mm", "Open-Meteo archive at the pass date")],
        )

    # 6. construction: a large HH jump (persistence needs a longer series than two dates)
    if _ge(hh, CONSTRUCTION_DHH_MIN) and group != "water":
        return _Hit(
            "construction",
            "HH jumped 5 dB or more (new hard surfaces or structures)",
            _JUDGMENT,
            hh,
            [Evidence("Persistence", "not checked", None, "", "needs more than two dates")],
        )

    # 7. crop cycle: with a crop mask, a big HV swing is farming, not disturbance
    if s.cdl_crop and hv is not None and abs(hv) >= CROP_DHV_ABS_MIN:
        return _Hit(
            "crop_cycle",
            "HV swung 2 dB or more on land the Cropland Data Layer marks as crop",
            _JUDGMENT,
            hv,
            [Evidence("Cropland mask", "crop", None, "", "USDA Cropland Data Layer")],
        )

    # 8. landslide: HV drop on a steep slope in a downslope shape (always low confidence)
    slope = _v(s.slope_deg)
    if (
        s.downslope_shape
        and slope is not None
        and slope > LANDSLIDE_SLOPE_MIN_DEG
        and _le(hv, LANDSLIDE_DHV_MAX)
    ):
        return _Hit(
            "landslide",
            "HV fell 3 dB or more on a slope over 15 degrees in a downslope shape",
            _ATBD + "; always low confidence",
            hv,
            [Evidence("Slope", round(slope, 1), None, "deg", "terrain slope")],
        )

    # 9. wet snow: both bands down near the melting point (low confidence only)
    t = _v(s.min_temp_c)
    if (
        _le(hh, SNOW_DROP_DB)
        and _le(hv, SNOW_DROP_DB)
        and t is not None
        and SNOW_TEMP_RANGE_C[0] <= t <= SNOW_TEMP_RANGE_C[1]
    ):
        return _Hit(
            "wet_snow",
            "HH and HV both fell 2 dB or more with a minimum temperature of 0-3 C",
            _JUDGMENT + "; C-band is the better snow sensor",
            min(hh, hv),
            [Evidence("Minimum temperature", round(t, 1), None, "C", "near the melting point")],
        )

    # 10. vegetation loss: HV drop. Forest or unknown cover reads as clear-cut, low cover as grass loss
    if _le(hv, CLEARCUT_DHV_MAX):
        lc = [Evidence("Land cover", s.landcover, None, "", "NLCD")] if s.landcover else []
        if group in ("forest", "unknown"):
            return _Hit("forest_loss", "HV fell 3 dB or more (canopy removed)", _ATBD, hv, lc)
        if group == "lowveg":
            return _Hit("low_veg_loss", "HV fell 3 dB or more over low vegetation", _ATBD, hv, lc)

    return _uncertain("No cause rule matched", "the L-band changes fit no cause rule")


def _classify_c(s: AreaStats) -> _Hit:
    """Rules for areas only Sentinel-1 saw: VV and VH changes drive the label."""
    vv, vh = _delta(s, "VV"), _delta(s, "VH")
    group = _landcover_group(s.landcover)
    low_veg = group == "lowveg" or s.cdl_crop
    lc = [Evidence("Land cover", s.landcover, None, "", "NLCD")] if s.landcover else []

    if _frozen(s) and _le(vv, FREEZE_DHH_MAX) and _le(vh, FREEZE_DHV_MAX):
        return _freeze_hit(s, vv, vh, "Sentinel-1")

    if _le(vh, C_VH_DROP_DB) and low_veg:
        if _fire(s):
            return _Hit(
                "burn",
                "Only Sentinel-1: VH fell 2 dB or more in low vegetation, with fire evidence",
                _SPEC,
                vh,
                _fire_evidence(s),
            )
        if s.cdl_crop:
            return _Hit(
                "harvest",
                "Only Sentinel-1: VH fell 2 dB or more on a Cropland Data Layer crop",
                _SPEC,
                vh,
                [Evidence("Cropland mask", "crop", None, "", "USDA Cropland Data Layer")],
            )
        return _Hit(
            "low_veg_loss", "Only Sentinel-1: VH fell 2 dB or more in low vegetation", _SPEC, vh, lc
        )

    slope = _v(s.slope_deg)
    flat_low = (
        _v(s.hand_m) is not None and _hand_ok(s) and (slope is None or slope <= FLAT_SLOPE_MAX_DEG)
    )
    if (_ge(vv, C_RISE_MIN_DB) or _ge(vh, C_RISE_MIN_DB)) and flat_low:
        rise = max(d for d in (vv, vh) if d is not None)
        return _Hit(
            "soil_wetting",
            "Only Sentinel-1: VV or VH rose 2 dB or more over flat, low-HAND ground",
            _SPEC,
            rise,
            [
                Evidence(
                    "Cause",
                    "possible surface water or wetting",
                    None,
                    "",
                    "possible surface water or wetting; C-band cannot tell water from wet soil here",
                )
            ]
            + _hand_evidence(s),
        )

    return _uncertain(
        "Only Sentinel-1 saw it and no C-band rule matched",
        "Changed, cause uncertain: only Sentinel-1 saw it",
    )


def _nan_if_missing(x: Any) -> float:
    v = _v(x)
    return float("nan") if v is None else v


def _feature_row(s: AreaStats) -> dict[str, Any]:
    """One row of the numbers the learned model sees (missing values are NaN)."""
    num = _nan_if_missing
    return {
        "dHH": num(s.dHH),
        "dHV": num(s.dHV),
        "dVV": num(s.dVV),
        "dVH": num(s.dVH),
        "pre_HH": num(s.pre_HH),
        "pre_HV": num(s.pre_HV),
        "post_HH": num(s.post_HH),
        "post_HV": num(s.post_HV),
        "landcover": s.landcover,
        "hand_m": num(s.hand_m),
        "slope_deg": num(s.slope_deg),
        "firms_count": int(s.firms_count),
        "agreement": s.agreement,
    }


def _apply_model(s: AreaStats, hit: _Hit, model: Any) -> _Hit:
    """Let the learned model relabel the area, but only for classes where it beat the rules.

    `model` needs `.winners` (classes where the model's held-out F1 beat the rules) and
    `.predict(DataFrame) -> array of class names`. Anything missing or failing keeps the rules.
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
    deltas = [abs(d) for d in (_delta(s, b) for b in ("HH", "HV", "VV", "VH")) if d is not None]
    note = f"rules alone said {hit.cls}; the learned model beat the rules on held-out states for {pred}"
    return _Hit(
        pred,
        "Learned model (held-out winner for this class)",
        "learned cause model",
        max(deltas) if deltas else None,
        [Evidence("Learned model", pred, None, "", note)],
    )


def classify(stats: AreaStats, model: Any = None) -> tuple[str, str, list[Evidence]]:
    """Label one change area: returns (class, confidence label, evidence).

    Areas only Sentinel-1 saw use the C-band rules; every other area uses the L-band rules.
    `model` is an optional learned `CauseModel`, used only for classes in its `winners`.
    """
    hit = _classify_c(stats) if stats.agreement == "C" else _classify_l(stats)
    if model is not None:
        hit = _apply_model(stats, hit, model)
    first = ("VV", "VH") if stats.agreement == "C" else _L_BANDS
    evidence = (
        [Evidence("Rule fired", hit.rule, None, "", hit.source)]
        + _band_evidence(stats, first)
        + hit.evidence
    )
    label = "Low" if hit.cls in _LOW_CAP else confidence_label(stats.frac_significant, hit.delta)
    return hit.cls, label, evidence

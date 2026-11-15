"""Cause rules: one test per row of the science.md rule table plus the C-only rules."""

import json
from types import SimpleNamespace

import numpy as np
import pytest

from sarstellar.rules import CLASSES, AreaStats, classify, confidence_label
from sarstellar.types import Evidence


def stats(**kw) -> AreaStats:
    return AreaStats(**kw)


def ev(evidence, label):
    """The first evidence entry with this label (fails the test if it is missing)."""
    for e in evidence:
        if e.label == label:
            return e
    raise AssertionError(f"no evidence labelled {label!r} in {[e.label for e in evidence]}")


def has_note(evidence, text):
    return any(text in e.note for e in evidence)


# ---- L-band rules ---------------------------------------------------------------------------


def test_clearcut():
    cls, label, evidence = classify(
        stats(dHV=-3.5, dHH=-0.5, ci={"HV": (-4.1, -2.9)}, frac_significant=0.9)
    )
    assert cls == "forest_loss"
    assert label == "High"
    hv = ev(evidence, "HV change")
    assert hv.value == pytest.approx(-3.5)
    assert hv.unit == "dB"
    assert hv.ci == [-4.1, -2.9]
    assert ev(evidence, "Rule fired").value  # the rule that fired is always reported


def test_clearcut_needs_a_3_db_hv_drop():
    cls, _, _ = classify(stats(dHV=-2.5, dHH=-0.5))
    assert cls == "uncertain"


def test_clearcut_on_grassland_is_low_veg_loss():
    cls, _, _ = classify(stats(dHV=-3.5, dHH=-0.5, landcover="Grassland/Herbaceous"))
    assert cls == "low_veg_loss"


def test_clearcut_in_forest_landcover():
    cls, _, _ = classify(stats(dHV=-3.5, dHH=-0.5, landcover="Evergreen Forest"))
    assert cls == "forest_loss"


def test_flooded_veg():
    cls, _, evidence = classify(stats(dHH=4.0, dHV=0.5))
    assert cls == "flooded_vegetation"
    assert ev(evidence, "HH change").value == pytest.approx(4.0)


def test_flooded_veg_post_state_check_when_levels_known():
    # HH after -8 dB, HV after -18 dB: ratio 10 dB > 9 dB, passes the ATBD cue
    ok, _, _ = classify(stats(dHH=4.0, dHV=0.5, post_HH=-8.0, post_HV=-18.0))
    assert ok == "flooded_vegetation"
    # HH after -10 dB, HV after -14 dB: HH is dim and the ratio is 4 dB, so no flooded-veg cue
    no, _, _ = classify(stats(dHH=4.0, dHV=0.5, post_HH=-10.0, post_HV=-14.0))
    assert no == "uncertain"


def test_flooded_veg_needs_low_hand_and_not_built_up():
    assert classify(stats(dHH=4.0, dHV=0.5, hand_m=40.0))[0] == "uncertain"
    assert classify(stats(dHH=4.0, dHV=0.5, hand_m=3.0))[0] == "flooded_vegetation"


def test_open_water():
    # HH after -21 dB, HV after -28 dB: product 1.3e-5 linear, below the 5e-5 ATBD value
    cls, _, evidence = classify(stats(dHH=-7.0, dHV=-6.0, post_HH=-21.0, post_HV=-28.0))
    assert cls == "flood_open_water"
    product = ev(evidence, "HH x HV after (linear)")
    assert product.value < 5e-5


def test_open_water_rejects_bright_water_surface_and_small_drops():
    # product 3.2e-4: too bright for calm open water (wind roughening, tarmac)
    assert (
        classify(stats(dHH=-7.0, dHV=-6.0, post_HH=-15.0, post_HV=-20.0))[0] != "flood_open_water"
    )
    # dark afterwards but HH only fell 4 dB
    assert (
        classify(stats(dHH=-4.0, dHV=-3.0, post_HH=-21.0, post_HV=-28.0))[0] != "flood_open_water"
    )


def test_open_water_needs_low_hand():
    cls, _, _ = classify(stats(dHH=-7.0, dHV=-6.0, post_HH=-21.0, post_HV=-28.0, hand_m=60.0))
    assert cls != "flood_open_water"


def test_burn_needs_fire_evidence():
    assert classify(stats(dHV=-3.0, dHH=-1.0, firms_count=0, in_fire_perimeter=False))[0] == (
        "forest_loss"
    )
    cls, _, evidence = classify(stats(dHV=-3.0, dHH=-1.0, firms_count=12))
    assert cls == "burn"
    assert ev(evidence, "FIRMS detections").value == 12


def test_burn_with_perimeter_only():
    assert classify(stats(dHV=-2.5, dHH=-0.5, in_fire_perimeter=True))[0] == "burn"


def test_burn_not_claimed_when_hh_rises():
    # dHH > 0 breaks the burn signature (down / down); fire evidence alone is not enough
    assert classify(stats(dHV=-3.0, dHH=1.5, firms_count=12))[0] != "burn"


def test_crop_cycle_on_cdl_crop():
    cls, _, _ = classify(stats(dHV=-3.0, dHH=-1.0, cdl_crop=True))
    assert cls == "crop_cycle"


def test_crop_with_fire_evidence_is_burn():
    assert classify(stats(dHV=-3.0, dHH=-1.0, cdl_crop=True, firms_count=4))[0] == "burn"


def test_soil_wetting_needs_rain():
    cls, _, evidence = classify(stats(dHH=2.0, dHV=2.5, rain_mm=12.0))
    assert cls == "soil_wetting"
    assert ev(evidence, "Rain").value == pytest.approx(12.0)
    assert classify(stats(dHH=2.0, dHV=2.5, rain_mm=0.0))[0] == "uncertain"
    assert classify(stats(dHH=2.0, dHV=2.5, rain_mm=None))[0] == "uncertain"


def test_soil_wetting_needs_flat_ratio_and_modest_rise():
    # HH rose 2 dB more than HV: a ratio change, not uniform wetting
    assert classify(stats(dHH=3.5, dHV=1.5, rain_mm=12.0))[0] != "soil_wetting"
    # +6 dB is beyond a wetting-sized rise
    assert classify(stats(dHH=6.0, dHV=5.5, rain_mm=12.0))[0] != "soil_wetting"


def test_construction():
    cls, _, _ = classify(stats(dHH=6.0, dHV=4.0))
    assert cls == "construction"
    assert classify(stats(dHH=6.0, dHV=1.0, landcover="Developed, Medium Intensity"))[0] == (
        "construction"
    )


def test_landslide_is_always_low_confidence():
    cls, label, evidence = classify(stats(dHH=-1.0, dHV=-4.5, slope_deg=28.0, downslope_shape=True))
    assert cls == "landslide"
    assert label == "Low"
    assert ev(evidence, "Slope").value == pytest.approx(28.0)


def test_steep_forest_loss_without_downslope_shape_is_not_a_landslide():
    assert classify(stats(dHH=-0.5, dHV=-4.5, slope_deg=28.0))[0] == "forest_loss"


def test_wet_snow_is_low_confidence_only():
    cls, label, _ = classify(stats(dHH=-3.0, dHV=-3.0, min_temp_c=1.0))
    assert cls == "wet_snow"
    assert label == "Low"


def test_freeze_suppressed():
    cls, label, evidence = classify(stats(dHH=-3.0, dHV=-3.0, min_temp_c=-4.0))
    assert cls == "uncertain"
    assert label == "Low"
    assert has_note(evidence, "possible freeze")
    assert ev(evidence, "Minimum temperature").value == pytest.approx(-4.0)


def test_freeze_does_not_hide_a_clearcut_or_a_fire():
    # a clear-cut leaves HH near flat, so a cold day does not suppress it
    assert classify(stats(dHH=-0.5, dHV=-3.5, min_temp_c=-4.0))[0] == "forest_loss"
    # a FIRMS hit is independent heat evidence
    assert classify(stats(dHH=-3.0, dHV=-3.0, min_temp_c=-4.0, firms_count=9))[0] == "burn"


def test_warm_both_down_is_forest_loss_not_freeze():
    assert classify(stats(dHH=-3.0, dHV=-3.0, min_temp_c=8.0))[0] == "forest_loss"


def test_freeze_up_is_never_emitted():
    assert "freeze_up" not in CLASSES
    assert len(CLASSES) == 12


# ---- C-only rules ---------------------------------------------------------------------------


def test_c_only_low_veg():
    base = {"agreement": "C", "dVH": -2.5, "dVV": -1.0, "landcover": "Grassland/Herbaceous"}
    cls, _, evidence = classify(stats(**base))
    assert cls == "low_veg_loss"
    assert ev(evidence, "VH change").value == pytest.approx(-2.5)
    assert classify(stats(**base, in_fire_perimeter=True))[0] == "burn"
    assert classify(stats(**base, firms_count=3))[0] == "burn"
    assert classify(stats(**base, cdl_crop=True))[0] == "harvest"


def test_c_only_crop_landcover_without_cdl_is_low_veg_loss():
    cls, _, _ = classify(stats(agreement="C", dVH=-2.5, landcover="Cultivated Crops"))
    assert cls == "low_veg_loss"


def test_c_only_vh_drop_under_2_db_is_uncertain():
    assert classify(stats(agreement="C", dVH=-1.5, landcover="grass"))[0] == "uncertain"


def test_c_only_vv_rise_on_flat_low_hand_ground():
    cls, _, evidence = classify(stats(agreement="C", dVV=3.0, dVH=1.0, hand_m=2.0, slope_deg=1.0))
    assert cls == "soil_wetting"
    assert has_note(evidence, "possible surface water")


def test_c_only_rise_on_high_ground_is_uncertain():
    assert classify(stats(agreement="C", dVV=3.0, dVH=1.0, hand_m=40.0, slope_deg=1.0))[0] == (
        "uncertain"
    )
    assert classify(stats(agreement="C", dVV=3.0, dVH=1.0, hand_m=2.0, slope_deg=20.0))[0] == (
        "uncertain"
    )
    assert classify(stats(agreement="C", dVV=3.0, dVH=1.0))[0] == "uncertain"  # HAND unknown


def test_c_only_other_is_uncertain():
    cls, label, evidence = classify(stats(agreement="C", dVH=-2.5, landcover="Evergreen Forest"))
    assert cls == "uncertain"
    assert label == "Low"
    assert has_note(evidence, "Sentinel-1-majority area")


def test_c_only_never_uses_l_band_rules():
    # strong L-band numbers on a C-only area must not trigger a flood or clear-cut label
    cls, _, _ = classify(stats(agreement="C", dHH=-8.0, dHV=-4.0, post_HH=-22.0, post_HV=-30.0))
    assert cls == "uncertain"


def test_no_bands_is_uncertain():
    assert classify(stats())[0] == "uncertain"
    assert classify(stats(agreement="L"))[0] == "uncertain"


# ---- confidence ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "frac, delta, expected",
    [
        (0.90, -3.5, "High"),
        (0.80, 3.0, "High"),  # both limits are inclusive
        (0.79, -3.5, "Medium"),
        (0.90, -2.5, "Medium"),  # many blocks significant but the drop is under 3 dB
        (0.50, -3.5, "Medium"),
        (0.49, -3.5, "Low"),
        (0.10, -9.0, "Low"),
    ],
)
def test_confidence_label_thresholds(frac, delta, expected):
    assert confidence_label(frac, delta) == expected


def test_classify_uses_area_fractions_for_confidence():
    assert classify(stats(dHV=-3.5, dHH=-0.5, frac_significant=0.9))[1] == "High"
    assert classify(stats(dHV=-3.5, dHH=-0.5, frac_significant=0.6))[1] == "Medium"
    assert classify(stats(dHV=-3.5, dHH=-0.5, frac_significant=0.3))[1] == "Low"


# ---- the optional learned model --------------------------------------------------------------


class FakeModel:
    def __init__(self, prediction, winners):
        self.prediction = prediction
        self.winners = winners
        self.seen = None

    def predict(self, df):
        self.seen = df
        return np.array([self.prediction])


def test_model_none_is_ignored():
    assert classify(stats(dHV=-3.5, dHH=-0.5), model=None)[0] == "forest_loss"


def test_model_used_only_for_winner_classes():
    model = FakeModel("construction", winners=["construction"])
    cls, _, evidence = classify(stats(dHV=-3.5, dHH=-0.5), model=model)
    assert cls == "construction"
    assert ev(evidence, "Learned model").value == "construction"
    assert len(model.seen) == 1  # it saw one row of features
    # the model predicts a class that did not beat the rules: the rules' label stays
    losing = FakeModel("construction", winners=["flood_open_water"])
    assert classify(stats(dHV=-3.5, dHH=-0.5), model=losing)[0] == "forest_loss"


def test_model_burn_is_accepted_only_with_fire_evidence():
    model = FakeModel("burn", winners=["burn"])
    # HH rose, so the burn rule does not fire; the rules say forest_loss
    base = {"dHV": -3.0, "dHH": 1.5}
    # no FIRMS, no perimeter: the rules' label stays (L-band area)
    assert classify(stats(**base), model=model)[0] == "forest_loss"
    assert classify(stats(**base, firms_count=0), model=model)[0] == "forest_loss"
    # with fire evidence the model's burn is accepted
    assert classify(stats(**base, firms_count=5), model=model)[0] == "burn"
    assert classify(stats(**base, in_fire_perimeter=True), model=model)[0] == "burn"


def test_model_burn_without_fire_evidence_is_rejected_on_c_only_areas_too():
    model = FakeModel("burn", winners=["burn"])
    c_only = {"agreement": "C", "dVH": -1.0, "landcover": "Evergreen Forest"}
    assert classify(stats(**c_only), model=model)[0] == "uncertain"
    assert classify(stats(**c_only, firms_count=3), model=model)[0] == "burn"


def test_model_harvest_and_crop_cycle_need_the_crop_mask():
    for pred in ("harvest", "crop_cycle"):
        model = FakeModel(pred, winners=[pred])
        no_crop = classify(stats(dHV=-3.5, dHH=-0.5), model=model)[0]
        assert no_crop == "forest_loss", pred  # rules' label kept
        c_only = classify(stats(agreement="C", dVH=-1.0), model=model)[0]
        assert c_only == "uncertain", pred
    # with a CDL crop the model's label is accepted (rules say crop_cycle on L, uncertain on C)
    harvest = FakeModel("harvest", winners=["harvest"])
    assert classify(stats(dHV=-3.5, dHH=-0.5, cdl_crop=True), model=harvest)[0] == "harvest"
    crop = FakeModel("crop_cycle", winners=["crop_cycle"])
    assert classify(stats(agreement="C", dVH=-1.0, cdl_crop=True), model=crop)[0] == "crop_cycle"


def test_model_cannot_override_freeze_suppression_or_invent_classes():
    cold = FakeModel("forest_loss", winners=["forest_loss"])
    assert classify(stats(dHH=-3.0, dHV=-3.0, min_temp_c=-4.0), model=cold)[0] == "uncertain"
    bogus = FakeModel("freeze_up", winners=["freeze_up"])
    assert classify(stats(dHV=-3.5, dHH=-0.5), model=bogus)[0] == "forest_loss"


def test_broken_model_falls_back_to_rules():
    class Broken:
        def __init__(self):
            self.winners = ["burn"]

        def predict(self, df):
            raise RuntimeError("model file missing")

    assert classify(stats(dHV=-3.5, dHH=-0.5), model=Broken())[0] == "forest_loss"
    assert classify(stats(dHV=-3.5, dHH=-0.5), model=SimpleNamespace())[0] == "forest_loss"


# ---- review fixes: permanent water, safe defaults, look-alikes, provenance --------------------


def test_open_water_signature_on_nlcd_open_water_is_not_a_new_flood():
    water = {"dHH": -7.0, "dHV": -6.0, "post_HH": -21.0, "post_HV": -28.0}
    assert classify(stats(**water))[0] == "flood_open_water"
    cls, label, evidence = classify(stats(**water, landcover="Open Water", frac_significant=0.9))
    assert cls == "uncertain"
    assert label == "Low"
    assert has_note(evidence, "permanent open water")


def test_default_area_stats_can_never_be_high_confidence():
    # frac_significant is unknown, so even a big, clean signature stays Low
    for kw in (
        {"dHV": -6.0, "dHH": -0.5},  # forest_loss
        {"dHH": 6.0, "dHV": 4.0},  # construction
        {"dHH": -9.0, "dHV": -8.0, "post_HH": -22.0, "post_HV": -30.0},  # flood_open_water
        {"agreement": "C", "dVH": -6.0, "landcover": "grass"},  # low_veg_loss
    ):
        cls, label, _ = classify(stats(**kw))
        assert cls != "uncertain", kw
        assert label == "Low", (cls, label)
    assert AreaStats().frac_significant is None
    assert AreaStats().downslope_shape is None
    assert classify(stats(dHV=-6.0, dHH=-0.5, frac_significant=float("nan")))[1] == "Low"
    assert classify(stats(dHV=-6.0, dHH=-0.5, frac_significant=0.9))[1] == "High"


def test_unknown_downslope_shape_means_no_landslide():
    cls, _, _ = classify(stats(dHV=-4.5, dHH=-1.0, slope_deg=28.0, downslope_shape=None))
    assert cls == "forest_loss"


def test_flooded_veg_with_a_crop_mask_is_capped_at_medium_with_lookalike_note():
    area = {"dHH": 4.0, "dHV": 0.5, "hand_m": 3.0, "frac_significant": 0.9}
    cls, label, evidence = classify(stats(**area))
    assert (cls, label) == ("flooded_vegetation", "High")  # clean case stays High
    assert not has_note(evidence, "rice paddy")
    cls, label, evidence = classify(stats(**area, cdl_crop=True))
    assert (cls, label) == ("flooded_vegetation", "Medium")
    assert has_note(evidence, "could also be rice paddy or new construction")


def test_flooded_veg_with_unknown_hand_is_capped_at_medium_with_lookalike_note():
    cls, label, evidence = classify(stats(dHH=4.0, dHV=0.5, frac_significant=0.9))
    assert (cls, label) == ("flooded_vegetation", "Medium")
    assert has_note(evidence, "could also be rice paddy or new construction")


def test_flooded_veg_with_high_hand_is_not_flooded_veg():
    assert classify(stats(dHH=4.0, dHV=0.5, hand_m=40.0, frac_significant=0.9))[0] != (
        "flooded_vegetation"
    )


def source_of(evidence) -> str:
    return ev(evidence, "Rule fired").note


def test_provenance_atbd_only_for_the_rules_that_implement_atbd_logic():
    # the 5e-5 product (inundation ATBD) and the flooded-veg post cues are ATBD values
    water = classify(stats(dHH=-7.0, dHV=-6.0, post_HH=-21.0, post_HV=-28.0))[2]
    assert "ATBD" in source_of(water) and "judgment" in source_of(water)
    # the two-date HV thresholds are not ATBD: the disturbance ATBD is a CUSUM on the series
    for kw in (
        {"dHV": -3.5, "dHH": -0.5},  # forest_loss
        {"dHV": -3.0, "dHH": -1.0, "firms_count": 12},  # burn
    ):
        note = source_of(classify(stats(**kw))[2])
        assert "research table" in note, kw
        assert "ATBD" not in note.replace("not NISAR ATBD", ""), kw
    # extensions and our own choices are labelled judgment, not ATBD
    low_veg = classify(stats(dHV=-3.5, dHH=-0.5, landcover="Grassland/Herbaceous"))[2]
    landslide = classify(stats(dHV=-4.5, dHH=-1.0, slope_deg=28.0, downslope_shape=True))[2]
    c_freeze = classify(stats(agreement="C", dVV=-1.5, dVH=-3.0, min_temp_c=-5.0))[2]
    for evidence in (low_veg, landslide, c_freeze):
        assert "judgment" in source_of(evidence)
        assert "ATBD" not in source_of(evidence)


def test_c_only_fire_evidence_beats_freeze_like_the_l_band_path():
    base = {"agreement": "C", "dVV": -1.5, "dVH": -3.0, "min_temp_c": -5.0, "landcover": "grass"}
    # same numbers on L-band: FIRMS wins over freeze
    assert classify(stats(dHH=-3.0, dHV=-3.0, min_temp_c=-5.0, firms_count=5))[0] == "burn"
    assert classify(stats(**base, firms_count=5))[0] == "burn"
    assert classify(stats(**base, in_fire_perimeter=True))[0] == "burn"


def test_c_only_freeze_is_suppressed_without_fire_evidence():
    base = {"agreement": "C", "dVV": -1.5, "dVH": -3.0, "min_temp_c": -5.0, "landcover": "grass"}
    cls, label, evidence = classify(stats(**base))
    assert (cls, label) == ("uncertain", "Low")
    assert has_note(evidence, "possible freeze")
    # a crop mask does not turn a frozen day into a harvest either
    assert classify(stats(**base, cdl_crop=True))[0] == "uncertain"
    # a warm day with the same numbers is low-vegetation loss
    assert classify(stats(**{**base, "min_temp_c": 8.0}))[0] == "low_veg_loss"


def test_missing_fire_count_is_zero_not_a_crash():
    assert classify(stats(dHV=-3.5, dHH=-0.5, firms_count=None))[0] == "forest_loss"
    assert classify(stats(dHV=-3.5, dHH=-0.5, firms_count=None, in_fire_perimeter=True))[0] == (
        "burn"
    )
    assert classify(stats(agreement="C", dVH=-2.5, landcover="grass", firms_count=None))[0] == (
        "low_veg_loss"
    )
    model = FakeModel("construction", winners=["construction"])
    assert classify(stats(dHV=-3.5, dHH=-0.5, firms_count=None), model=model)[0] == "construction"


# ---- evidence is plain data ------------------------------------------------------------------


def test_evidence_is_json_serialisable():
    _, _, evidence = classify(
        stats(dHH=-7.0, dHV=-6.0, post_HH=-21.0, post_HV=-28.0, ci={"HH": (-8.0, -6.0)})
    )
    assert evidence and all(isinstance(e, Evidence) for e in evidence)
    json.dumps([e.to_json() for e in evidence])  # no numpy scalars or tuples that break JSON


def test_nan_inputs_are_treated_as_missing():
    cls, _, _ = classify(stats(dHH=float("nan"), dHV=float("nan")))
    assert cls == "uncertain"

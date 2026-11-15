"""Scorecard maths on synthetic block tables: metrics, PR curves, bootstraps, fusion, labels.

A block table is a DataFrame with one row per 1-ha block: `site`, `state`, `split`, `y` (the
reference says this class), per-detector scores `s_<det>` (higher means more change), p-values
`p_L`, `p_C`, `p_L30` and relative changes `rel_HH` ... `rel_VH`. Nothing here touches a network.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from sarstellar import scoring
from sarstellar.types import Grid

GRID = Grid(epsg=32610, xmin=0.0, xmax=1000.0, ymin=0.0, ymax=1000.0, res=100.0)  # 10 x 10 blocks


# --- metrics at the default operating point -----------------------------------------------------


def test_metrics_known_counts():
    p = [1e-6] * 6 + [0.9] * 4
    rel_hh = [-3.0] * 4 + [0.5] * 2 + [0.0] * 4  # two significant blocks fail the 2 dB gate
    y = [1, 1, 1, 0, 1, 0, 1, 0, 0, 0]
    df = pd.DataFrame({"site": "a", "y": np.array(y, bool), "p_L": p, "rel_HH": rel_hh,
                       "rel_HV": 0.0})
    m = scoring.metrics(df, "L", 2.0)
    assert m["n_flags"] == 4 and m["n_ref"] == 5
    assert m["precision"] == pytest.approx(0.75)
    assert m["recall"] == pytest.approx(0.6)
    assert m["f1"] == pytest.approx(2 * 0.75 * 0.6 / 1.35)


def test_metrics_no_flags_is_zero_not_nan():
    df = pd.DataFrame({"site": "a", "y": [True, False, True], "p_L": [0.9, 0.8, 0.7],
                       "rel_HH": 0.0, "rel_HV": 0.0})
    m = scoring.metrics(df, "L", 2.0)
    assert m["n_flags"] == 0 and m["precision"] == 0.0 and m["recall"] == 0.0 and m["f1"] == 0.0


def test_bh_runs_per_site():
    # 3 weak p-values in a box of 3 are significant together; mixed into a huge box they are not
    small = pd.DataFrame({"site": "s", "y": True, "p_L": [0.01, 0.012, 0.014],
                          "rel_HH": -3.0, "rel_HV": 0.0})
    big = pd.DataFrame({"site": "b", "y": False, "p_L": np.full(1000, 0.5),
                        "rel_HH": -3.0, "rel_HV": 0.0})
    df = pd.concat([small, big], ignore_index=True)
    assert scoring.flags(df, "L").iloc[:3].all()


# --- PR curves ----------------------------------------------------------------------------------


def test_perfect_ranking_has_auprc_one_and_random_has_prevalence():
    rng = np.random.default_rng(0)
    y = rng.random(20000) < 0.2
    assert scoring.average_precision(y.astype(float), y) == pytest.approx(1.0)
    assert scoring.average_precision(rng.random(20000), y) == pytest.approx(0.2, abs=0.02)


def test_pr_curve_ends_at_full_recall_and_matches_ap():
    df = pd.DataFrame({"y": [True, False, True, False, False], "s_L": [5.0, 4.0, 3.0, 2.0, 1.0]})
    curve = scoring.pr_curve(df, "L")
    recalls = [r for r, _, _ in curve]
    assert recalls == sorted(recalls) and recalls[-1] == 1.0
    assert curve[0][:2] == (0.5, 1.0)  # the top block is a hit
    assert scoring.auprc(curve) == pytest.approx(scoring.average_precision(df["s_L"], df["y"]))
    assert scoring.auprc(curve) == pytest.approx(0.5 * 1.0 + 0.5 * (2 / 3))


def test_ties_are_not_ordered_by_row_position():
    # an all-tied detector must score the prevalence whatever order the rows come in
    y = np.array([True] * 10 + [False] * 90)
    assert scoring.average_precision(np.zeros(100), y) == pytest.approx(0.1)
    assert scoring.average_precision(np.zeros(100), y[::-1]) == pytest.approx(0.1)


def test_equal_recall_interpolates():
    a = [(0.0, 1.0, 9.0), (0.5, 0.8, 5.0), (1.0, 0.2, 1.0)]
    b = [(0.2, 0.6, 7.0), (0.6, 0.4, 3.0)]
    pa, pb = scoring.at_equal_recall(a, b, 0.25)
    assert pa == pytest.approx(0.9)  # halfway between (0, 1.0) and (0.5, 0.8)
    assert pb == pytest.approx(0.575)  # one eighth of the way from recall 0.2 to 0.6
    assert scoring.at_equal_recall(a, b, 0.5)[0] == pytest.approx(0.8)


# --- bootstraps ---------------------------------------------------------------------------------


def _sites_df(n_sites=20, per=50, seed=1):
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(n_sites):
        y = rng.random(per) < 0.3
        rows.append(pd.DataFrame({"site": f"s{s}", "y": y,
                                  "s_A": rng.normal(size=per) + 1.0 * y,
                                  "s_B": rng.normal(size=per) + 1.0 * y}))
    return pd.concat(rows, ignore_index=True)


def _ap(df, det):
    return scoring.average_precision(df[f"s_{det}"].to_numpy(), df["y"].to_numpy())


def test_bootstrap_ci_brackets_point():
    df = _sites_df()
    point = _ap(df, "A")
    lo, hi = scoring.bootstrap_ci(df, lambda d: _ap(d, "A"), n=200)
    assert lo <= point <= hi and hi - lo > 0


def test_bootstrap_resamples_whole_sites():
    seen = []
    scoring.bootstrap_ci(_sites_df(5, 10), lambda d: seen.append(len(d)) or 0.0, n=20)
    assert all(n % 10 == 0 for n in seen)


def test_paired_bootstrap_detects_gain():
    rng = np.random.default_rng(2)
    df = _sites_df(15, 60, seed=3)
    df["s_B"] = df["y"] * 2.0 + rng.normal(scale=0.1, size=len(df))  # B ranks every site well
    out = scoring.paired_bootstrap_delta(df, "A", "B", _ap, n=300)
    assert out["delta"] > 0.2 and out["ci_low"] > 0 and out["p_gt0"] > 0.99


def test_paired_bootstrap_null():
    df = _sites_df(15, 60, seed=4)
    df["s_B"] = df["s_A"]
    out = scoring.paired_bootstrap_delta(df, "A", "B", _ap, n=300)
    assert out["delta"] == 0 and out["ci_low"] <= 0 <= out["ci_high"]
    # two different, equally good detectors: the interval also straddles zero
    out = scoring.paired_bootstrap_delta(_sites_df(30, 60, seed=5), "A", "B", _ap, n=300)
    assert out["ci_low"] < 0 < out["ci_high"]


# --- the split ----------------------------------------------------------------------------------


def _fake_sites():
    kinds = ["forest_loss", "fire", "flood", "crops", "stable"]
    states = ["IN", "AL", "WA", "OR", "CA", "TX", "GA", "MN", "VA", "FL", "NC", "ID"]
    sites = []
    for i, st in enumerate(states):
        for k in kinds:
            if k == "flood" and st not in ("IN", "AL", "FL", "TX"):
                continue
            sites += [{"id": f"{k}-{st}-{j}", "kind": k, "state": st, "bbox": [0, 0, 1, 1]}
                      for j in range(1 + (i % 2))]
    return sites


def test_holdout_by_state():
    sites = _fake_sites()
    held = scoring.choose_holdout_states(sites, seed=7)
    out = scoring.assign_split(sites, held)
    train = {s["state"] for s in out if s["split"] == "train"}
    hold = {s["state"] for s in out if s["split"] == "holdout"}
    assert hold == set(held) and not (train & hold)
    for kind in ("forest_loss", "fire", "flood", "crops", "stable"):
        assert any(s["kind"] == kind and s["split"] == "holdout" for s in out), kind
    assert {"IN", "AL"} & hold  # flood has holdout sites from the big flood states
    assert scoring.choose_holdout_states(sites, seed=7) == held  # fixed seed, same answer
    assert 0.15 < sum(s["split"] == "holdout" for s in out) / len(out) < 0.5


# --- fusion -------------------------------------------------------------------------------------


def test_fisher_combines():
    both = scoring.fisher_p(np.array([0.05]), np.array([0.05]))
    assert both[0] < 0.05 and both[0] == pytest.approx(0.0175, abs=0.001)
    out = scoring.fisher_p(np.array([0.03, 0.2, np.nan]), np.array([np.nan, np.nan, 0.4]))
    assert out[0] == 0.03 and out[1] == 0.2 and out[2] == 0.4  # falls back to the other band
    assert np.isnan(scoring.fisher_p(np.array([np.nan]), np.array([np.nan]))[0])


def test_bonferroni_is_twice_the_min_and_falls_back():
    out = scoring.bonferroni_p(np.array([0.01, 0.4, np.nan]), np.array([0.2, 0.3, 0.05]))
    assert out[0] == pytest.approx(0.02) and out[1] == pytest.approx(0.6) and out[2] == 0.05
    assert scoring.bonferroni_p(np.array([0.7]), np.array([0.8]))[0] == 1.0


def _fusion_df(n=3000, seed=0, split="train"):
    rng = np.random.default_rng(seed)
    y = rng.random(n) < 0.3
    df = pd.DataFrame({
        "site": rng.integers(0, 6, n).astype(str), "state": "WA", "split": split, "kind": "fire",
        "label": np.where(y, "burn", "none"), "y": y,
    })
    for band, strength in (("HH", 0.3), ("HV", 1.0), ("VV", 0.2), ("VH", 0.8)):
        df[f"rel_{band}"] = rng.normal(size=n) - strength * 2.0 * y
    df["p_L"] = 10.0 ** -np.clip(rng.normal(1.0, 1.0, n) + 2.0 * y, 0.0, 30)
    df["p_C"] = 10.0 ** -np.clip(rng.normal(1.0, 1.0, n) + 1.0 * y, 0.0, 30)
    return df


def test_logistic_fit_uses_train_only():
    df = _fusion_df()
    scoring.fit_logistic_fusion(df)  # train rows only: fine
    bad = pd.concat([df, _fusion_df(50, seed=1, split="holdout")], ignore_index=True)
    with pytest.raises(ValueError, match="holdout"):
        scoring.fit_logistic_fusion(bad)


def test_logistic_learns_and_ranks_better_than_chance():
    train, test = _fusion_df(4000, seed=1), _fusion_df(4000, seed=2, split="holdout")
    model = scoring.fit_logistic_fusion(train)
    assert model.coef_.shape == (len(model.features),)
    s = model.score(test)
    assert scoring.average_precision(s, test["y"].to_numpy()) > 0.6
    prob = model.predict_proba(test)
    assert prob.min() >= 0 and prob.max() <= 1
    # a one-sensor model has no access to the other sensor's columns
    l_only = scoring.fit_logistic_fusion(train, sensors="L")
    assert all("VV" not in f and "VH" not in f and "_C" not in f for f in l_only.features)


def test_logistic_threshold_caps_stable_false_alarms():
    train = _fusion_df(6000, seed=3)
    stable = _fusion_df(2000, seed=4)
    stable["y"], stable["label"], stable["kind"] = False, "stable", "stable"
    for col in ("rel_HH", "rel_HV", "rel_VV", "rel_VH"):
        stable[col] = np.random.default_rng(5).normal(size=len(stable))
    stable["p_L"] = stable["p_C"] = np.random.default_rng(6).random(len(stable))
    both = pd.concat([train, stable], ignore_index=True)
    model = scoring.fit_logistic_fusion(both, fa_target=0.01)
    fa = (model.predict_proba(stable) >= model.threshold).mean()
    assert fa <= 0.011


# --- labels -------------------------------------------------------------------------------------


class _Fetch:
    """Stand-ins for the four reference sources, each answering with a fixed block array."""

    def __init__(self, **arrays):
        self.arrays, self.calls = arrays, []

    def dist_hls_loss(self, grid, start, end):
        self.calls.append(("loss", start, end))
        return self.arrays["loss"]

    def dswx_water(self, grid, when):
        self.calls.append(("water", when))
        return self.arrays["pre" if when == date(2026, 7, 26) else "post"]

    def cdl_fraction(self, grid):
        return self.arrays["crop"]

    def perimeters(self, site):
        return self.arrays.get("perims", [])


def _site(kind, **extra):
    return {"id": f"{kind}-1", "kind": kind, "bbox": [0, 0, 1, 1], "state": "WA",
            "ref_window": ["2026-07-16", "2026-08-30"],
            "meta": {"pair_dates": ["2026-07-26", "2026-08-19"]}, **extra}


def test_labels_forest_loss():
    loss = np.zeros(GRID.shape)
    loss[:2] = 0.6
    loss[5, 5] = np.nan
    lab = scoring.block_labels(_site("forest_loss"), GRID, _Fetch(loss=loss))
    assert (lab[:2] == "forest_loss").all() and lab[3, 3] == "none" and lab[5, 5] == ""
    assert lab.shape == GRID.shape and lab.dtype.kind == "U"


def test_labels_flood_needs_a_gain_between_the_two_passes():
    pre, post = np.zeros(GRID.shape), np.zeros(GRID.shape)
    post[:3] = 0.9  # new water
    pre[3] = 0.9
    post[3] = 0.95  # permanent water: not a flood
    pre[4], post[4] = np.nan, 0.9  # unknown before: ambiguous, not a negative
    post[6] = np.nan  # no after-image
    lab = scoring.block_labels(_site("flood"), GRID, _Fetch(pre=pre, post=post))
    assert (lab[:3] == "flood_open_water").all() and lab[3, 0] == "none"
    assert lab[4, 0] == "" and lab[6, 0] == "" and lab[8, 0] == "none"


def test_labels_crops_and_stable():
    crop = np.zeros(GRID.shape)
    crop[:, :4] = 0.9
    crop[9, 9] = np.nan
    lab = scoring.block_labels(_site("crops"), GRID, _Fetch(crop=crop))
    assert (lab[:, :4] == "crop_cycle").all() and lab[0, 8] == "none" and lab[9, 9] == ""
    assert (scoring.block_labels(_site("stable"), GRID, _Fetch()) == "stable").all()


def test_labels_fire_uses_the_perimeter_mask(monkeypatch):
    inside = np.zeros(GRID.shape, bool)
    inside[2:5] = True
    monkeypatch.setattr(scoring.refs_scoring, "nifc_mask", lambda grid, perims: inside)
    lab = scoring.block_labels(_site("fire"), GRID, _Fetch(perims=[{"type": "Polygon"}]))
    assert (lab[2:5] == "burn").all() and lab[0, 0] == "none"

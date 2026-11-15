"""Offline proof that the report preserves the fixed geographic holdout and common cohort."""

import json

import numpy as np
import pandas as pd
import pytest
from modal_app.scorecard_report import build_report

from sarstellar import scoring


def _table():
    rng = np.random.default_rng(19)
    parts, sites = [], []
    for split, state in (("train", "WA"), ("holdout", "IN")):
        for kind in (*scoring.KIND_CLASS, "stable"):
            for repeat in range(2):
                site = f"{split}-{kind}-{repeat}"
                y = np.r_[np.ones(20, bool), np.zeros(20, bool)]
                if kind == "stable":
                    y[:] = False
                cls = scoring.KIND_CLASS.get(kind, "stable")
                labels = np.where(y, cls, "stable" if kind == "stable" else "none")
                df = pd.DataFrame({"site": site, "state": state, "kind": kind,
                                   "split": split, "label": labels, "y": y,
                                   "landcover": "forest", "comparable": True})
                for pol in ("HH", "HV", "VV", "VH", "HH30", "HV30"):
                    df[f"rel_{pol}"] = rng.normal(size=len(df)) - 2 * y
                for band in ("L", "C", "L30"):
                    df[f"p_{band}"] = 10 ** -(rng.random(len(df)) + 2 * y)
                    # C is best on training; L is best on holdout. Selection must use training.
                    good = (band == "C" and split == "train") or (band == "L" and split == "holdout")
                    df[f"s_{band}"] = 10 * y + rng.random(len(df)) if good else rng.random(len(df))
                df["p_Ls"], df["s_L_series"] = df.p_L, df.s_L
                for det in ("fused_fisher", "fused_bonferroni"):
                    df[f"s_{det}"] = scoring.neg_log10(scoring.pvalue(df, det))
                for det in ("L", "C", "L30", "L_series", "fused_fisher", "fused_bonferroni"):
                    df[f"flag_{det}"] = scoring.flags(df, det)
                parts.append(df)
                sites.append({"id": site, "kind": kind, "state": state, "split": split,
                              "bbox": [-120, 40, -119.9, 40.1]})
    return pd.concat(parts, ignore_index=True), sites


def test_report_selects_on_training_and_does_not_claim_small_batch_complete():
    table, sites = _table()
    result = build_report(table, sites, n_boot=10)
    assert len(result["fusion"]) == 4
    assert all(row["best_single"] == "C" for row in result["fusion"])
    assert result["fusion_model"]["training_sites"] == 10
    assert result["holdout_states"] == ["IN"]
    assert result["status"] == "incomplete"
    assert result["adequacy"]["meets_site_target"] is False
    assert {r["landcover"] for r in result["classes"]} == {"all", "forest"}
    json.dumps(result, allow_nan=False)


def test_common_cohort_excludes_missing_sensor_and_keeps_counts_equal():
    table, sites = _table()
    table.loc[table.split.eq("holdout") & table.kind.eq("fire"), "comparable"] = False
    result = build_report(table, sites, n_boot=5)
    assert "burn" not in {r["class"] for r in result["classes"]}
    assert len(result["excluded_sites"]) == 2
    assert all(s["status"] == "excluded" for s in result["attempted_sites"]
               if s["split"] == "holdout" and s["kind"] == "fire")
    assert result["n_processed_sites"] == 20
    assert result["n_sites"] == result["n_comparable_sites"] == len(result["sites"]) == 18
    assert result["n_holdout_sites"] == 8
    for cls in {r["class"] for r in result["classes"]}:
        counts = {r["n_ref"] for r in result["classes"]
                  if r["class"] == cls and r["landcover"] == "all"}
        assert len(counts) == 1


def test_all_failed_batch_is_explicit_and_json_serializable():
    _, sites = _table()
    result = build_report(pd.DataFrame(), sites, failures=[{"id": sites[0]["id"], "error": "IOError"}])
    assert result["n_sites"] == 0 and result["status"] == "incomplete"
    assert result["classes"] == [] and result["fusion"] == []
    assert result["failed_sites"][0]["error"] == "IOError"
    json.dumps(result, allow_nan=False)


def test_displayed_holdout_states_are_evaluated_without_changing_the_planned_split():
    table, sites = _table()
    table.loc[table.split.eq("holdout"), "comparable"] = False
    result = build_report(table, sites, n_boot=5)
    assert result["holdout_states"] == []
    assert result["planned_holdout_states"] == ["IN"]
    assert result["n_holdout_sites"] == 0
    assert all(s["split"] == "train" for s in result["sites"])
    assert sum(s["split"] == "holdout" for s in result["attempted_sites"]) == 10


def test_logistic_rejects_missing_split_and_unknown_split():
    table, _ = _table()
    with pytest.raises(ValueError, match="holdout"):
        scoring.fit_logistic_fusion(table.drop(columns="split"))
    table["split"] = "unknown"
    with pytest.raises(ValueError, match="holdout"):
        scoring.fit_logistic_fusion(table)


def test_empty_curve_and_nan_bootstrap_are_reported_as_unavailable():
    assert np.isnan(scoring.at_equal_recall([], [], 0.5)[0])
    df = pd.DataFrame({"site": ["a", "b"]})
    result = scoring.paired_bootstrap_delta(df, "a", "b", lambda *_: np.nan, n=5)
    assert result["n_valid_draws"] == 0 and np.isnan(result["p_gt0"])

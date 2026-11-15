"""Fast weighted AP bootstraps must agree with explicitly copied sampled sites."""

import numpy as np
import pandas as pd
import pytest

from sarstellar import scoring
from sarstellar.scoring_bootstrap import bootstrap_ap, paired_ap_delta


def _ap(frame, det):
    return scoring.average_precision(frame[f"s_{det}"], frame.y)


def _frame(seed=3):
    rng = np.random.default_rng(seed)
    sites = np.repeat(["z", "a", "m", "b", "x"], [7, 11, 3, 8, 4])
    frame = pd.DataFrame({"site": sites, "y": rng.random(len(sites)) < 0.4})
    # Deliberate ties across sites; duplicate DataFrame indices must not affect grouping.
    frame["s_A"] = rng.integers(0, 5, len(frame)).astype(float)
    frame["s_B"] = rng.integers(0, 5, len(frame)).astype(float)
    frame.index = np.arange(len(frame)) // 2
    return frame.iloc[rng.permutation(len(frame))]


@pytest.mark.parametrize("seed", [0, 5, 21])
def test_ci_matches_generic_with_ties_and_unequal_sites(seed):
    frame = _frame()
    expected = scoring.bootstrap_ci(frame, lambda d: _ap(d, "A"), n=100, seed=seed)
    assert bootstrap_ap(frame, "A", n=100, seed=seed) == pytest.approx(expected, abs=1e-14)


@pytest.mark.parametrize("seed", [0, 5, 21])
def test_paired_delta_matches_generic_with_ties(seed):
    frame = _frame()
    expected = scoring.paired_bootstrap_delta(frame, "A", "B", _ap, n=100, seed=seed)
    assert paired_ap_delta(frame, "A", "B", n=100, seed=seed) == pytest.approx(expected)


def test_undefined_draws_match_generic_and_identical_detector_is_zero():
    frame = pd.DataFrame({"site": ["positive", "negative"], "y": [True, False],
                          "s_A": [0.0, 1.0], "s_B": [1.0, 0.0]})
    expected = scoring.paired_bootstrap_delta(frame, "A", "B", _ap, n=100, seed=4)
    actual = paired_ap_delta(frame, "A", "B", n=100, seed=4)
    assert actual == pytest.approx(expected)
    assert actual["n_valid_draws"] < 100
    null = paired_ap_delta(frame, "A", "A", n=100, seed=4)
    assert null["delta"] == null["ci_low"] == null["ci_high"] == null["p_gt0"] == 0


def test_missing_scores_have_same_ap_filtering():
    frame = _frame()
    frame.iloc[::3, frame.columns.get_loc("s_A")] = np.nan
    expected = scoring.bootstrap_ci(frame, lambda d: _ap(d, "A"), n=100, seed=2)
    assert bootstrap_ap(frame, "A", n=100, seed=2) == pytest.approx(expected)


def test_all_undefined_returns_nan_interval_and_zero_valid_draws():
    frame = pd.DataFrame({"site": ["a", "b"], "y": [False, False],
                          "s_A": [1.0, 2.0], "s_B": [2.0, 1.0]})
    assert np.isnan(bootstrap_ap(frame, "A", n=5)).all()
    actual = paired_ap_delta(frame, "A", "B", n=5)
    assert actual["n_valid_draws"] == 0
    assert all(np.isnan(v) for k, v in actual.items() if k != "n_valid_draws")


def test_custom_cluster_column_and_alpha_match_generic():
    frame = _frame().rename(columns={"site": "cluster"})
    expected = scoring.bootstrap_ci(frame, lambda d: _ap(d, "A"), n=100,
                                    by="cluster", seed=8, alpha=0.2)
    assert bootstrap_ap(frame, "A", n=100, by="cluster", seed=8,
                        alpha=0.2) == pytest.approx(expected)

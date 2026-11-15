"""Fast site bootstraps for average precision, equivalent to copying sampled sites.

Scores are sorted once. Each draw samples whole sites with replacement and uses their
multiplicities as integer row weights. Tied scores remain a single threshold, including when
some of their sites are absent from a draw. No fitting or detector selection happens here.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class _RankedAP:
    sites: np.ndarray
    positive: np.ndarray
    starts: np.ndarray

    @classmethod
    def prepare(cls, frame: pd.DataFrame, detector: str, site_codes: np.ndarray):
        scores = frame[f"s_{detector}"].to_numpy(dtype=float)
        keep = np.flatnonzero(np.isfinite(scores))
        order = keep[np.argsort(-scores[keep], kind="stable")]
        sorted_scores = scores[order]
        starts = (np.r_[0, np.flatnonzero(sorted_scores[1:] != sorted_scores[:-1]) + 1]
                  if order.size else np.array([], dtype=int))
        return cls(site_codes[order], frame["y"].to_numpy(dtype=bool)[order], starts)

    def evaluate(self, multiplicity: np.ndarray) -> float:
        if not self.sites.size:
            return float("nan")
        weights = multiplicity[self.sites]
        # Sum within tied-score thresholds before calculating cumulative TP and recall.
        positive = np.add.reduceat(weights * self.positive, self.starts)
        counts = np.add.reduceat(weights, self.starts)
        n_positive = int(positive.sum())
        if not n_positive:
            return float("nan")
        tp = np.cumsum(positive)
        total = np.cumsum(counts)
        precision = np.divide(tp, total, out=np.zeros(len(tp), dtype=float), where=total > 0)
        return float(np.sum(positive * precision) / n_positive)


def _sites(frame: pd.DataFrame, by: str) -> tuple[np.ndarray, int]:
    if frame.empty or frame[by].isna().any():
        raise ValueError("AP site bootstrap needs nonempty rows with a site for every row")
    groups = list(frame.groupby(by, sort=False, observed=True).indices.values())
    codes = np.empty(len(frame), dtype=np.intp)
    for code, indexes in enumerate(groups):
        codes[indexes] = code
    return codes, len(groups)


def _draws(n_sites: int, n: int, seed: int):
    if n < 1:
        raise ValueError("bootstrap needs at least one draw")
    rng = np.random.default_rng(seed)
    for _ in range(n):
        yield np.bincount(rng.integers(0, n_sites, n_sites), minlength=n_sites)


def _interval(values: np.ndarray, alpha: float) -> tuple[float, float]:
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between zero and one")
    finite = values[np.isfinite(values)]
    if not finite.size:
        return float("nan"), float("nan")
    lo, hi = np.percentile(finite, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(lo), float(hi)


def bootstrap_ap(frame: pd.DataFrame, detector: str, n: int = 500, by: str = "site",
                 seed: int = 0, alpha: float = 0.05) -> tuple[float, float]:
    """Percentile CI for AP, resampling sites exactly as scoring.bootstrap_ci does.

    Undefined draws (no reference positives with a finite score) are omitted from the interval.
    """
    codes, n_sites = _sites(frame, by)
    ranked = _RankedAP.prepare(frame, detector, codes)
    values = np.array([ranked.evaluate(w) for w in _draws(n_sites, n, seed)])
    return _interval(values, alpha)


def paired_ap_delta(frame: pd.DataFrame, det_a: str, det_b: str, n: int = 1000,
                    by: str = "site", seed: int = 0, alpha: float = 0.05) -> dict:
    """AP(B) minus AP(A), with both detectors evaluated on the same sampled sites.

    Missing scores follow scoring.average_precision's filtering. Callers must use the shared
    finite-score cohort when comparing detectors. p_gt0 uses only defined paired draws.
    """
    codes, n_sites = _sites(frame, by)
    a, b = (_RankedAP.prepare(frame, det, codes) for det in (det_a, det_b))
    values = np.array([b.evaluate(w) - a.evaluate(w) for w in _draws(n_sites, n, seed)])
    lo, hi = _interval(values, alpha)
    finite = values[np.isfinite(values)]
    once = np.ones(n_sites, dtype=int)
    return {"delta": b.evaluate(once) - a.evaluate(once), "ci_low": lo, "ci_high": hi,
            "p_gt0": float(np.mean(finite > 0)) if finite.size else float("nan"),
            "n_valid_draws": int(finite.size)}

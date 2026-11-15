"""Scorecard maths: reference labels, operating-point metrics, PR curves, bootstraps, fusion.

A block table is a pandas DataFrame with one row per 1-ha block. Columns used here:

    site, state, split, kind, label   which site / reference class the block belongs to
    y                                 True when the reference says this class (per class frame)
    p_L, p_C, p_L30, p_Ls             omnibus p-values: L-band pair, C-band pair, L at 30 m, L series
    rel_HH, rel_HV, rel_VV, rel_VH    relative change in dB (scene shift removed)
    s_<det>                           rank score of detector <det>, higher means more change

Headline comparisons are rank-based: AUPRC and precision at equal recall sweep a threshold over
the score, so they do not depend on whether a p-value is well calibrated (Ruling R12) or on the
ENL scale of a band (Sentinel-1 is conservative at the default operating point on low-ENL
ground). `metrics` and `flags` give the default operating point (BH-FDR q = 0.05 inside each
site's box AND an |effect| of at least 2 dB) and are always reported separately from the sweeps.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from scipy import special

from . import detect, refs, refs_scoring
from .types import Grid

__all__ = [
    "BAND_POLS",
    "KIND_CLASS",
    "MIN_DB",
    "FusionModel",
    "Q",
    "assign_split",
    "at_equal_recall",
    "auprc",
    "average_precision",
    "block_labels",
    "bonferroni_p",
    "bootstrap_ci",
    "choose_holdout_states",
    "fisher_p",
    "fit_logistic_fusion",
    "flags",
    "metrics",
    "neg_log10",
    "paired_bootstrap_delta",
    "pr_curve",
    "pvalue",
]

Q = 0.05  # BH-FDR level of the default operating point
MIN_DB = 2.0  # minimum |relative change| of the default operating point
NLP_CAP = 40.0  # -log10 p is capped here (p underflows to 0 for huge changes)

KIND_CLASS = {
    "forest_loss": "forest_loss",
    "fire": "burn",
    "flood": "flood_open_water",
    "crops": "crop_cycle",
}
BAND_POLS = {  # the polarisations whose |relative change| gates each detector
    "L": ("HH", "HV"), "L30": ("HH", "HV"), "L_series": ("HH", "HV"), "C": ("VV", "VH"),
    "fused_fisher": ("HH", "HV", "VV", "VH"), "fused_bonferroni": ("HH", "HV", "VV", "VH"),
}
_P_COL = {"L": "p_L", "C": "p_C", "L30": "p_L30", "L_series": "p_Ls"}


# --- reference labels ---------------------------------------------------------------------------


class _DefaultFetch:
    """The four reference sources, straight from `refs_scoring` (network)."""

    def __init__(self, fs=None):
        self.fs = fs

    def dist_hls_loss(self, grid, start, end):
        return refs_scoring.dist_hls_loss(grid, start, end, fs=self.fs)

    def dswx_water(self, grid, when):
        return refs_scoring.dswx_water(grid, when, fs=self.fs)

    def cdl_fraction(self, grid):
        return refs_scoring.cdl_fraction(grid, refs_scoring.CDL_CULTIVATED)

    def perimeters(self, site):
        return [p["geometry"] for p in refs.nifc_perimeters(site["bbox"])]


def _day(text) -> date:
    return text if isinstance(text, date) else date.fromisoformat(str(text)[:10])


def block_labels(site: dict, grid: Grid, fetch=None) -> np.ndarray:
    """One string per block: the reference class, "none" (the reference says no such change),
    "stable" (a stable-ground site) or "" (the reference has no data there: never scored).

    forest_loss  at least 50% of the block's DIST-ALERT-HLS pixels lost >= 50% vegetation in the
                 site's reference window
    burn         the block centre lies inside a NIFC/WFIGS perimeter
    flood        DSWx water gain: water after (>= 0.5 of the block) and not before (< 0.2);
                 unknown "before" over water is "" (ambiguous), not a negative
    crop_cycle   at least half the block is cultivated in the Cropland Data Layer
    """
    fetch = fetch or _DefaultFetch()
    kind = site["kind"]
    out = np.full(grid.shape, "", dtype="<U16")
    if kind == "stable":
        out[:] = "stable"
        return out
    cls = KIND_CLASS[kind]
    if kind == "forest_loss":
        w0, w1 = (_day(d) for d in site["ref_window"])
        frac = np.asarray(fetch.dist_hls_loss(grid, w0, w1), dtype=float)
        known, pos = np.isfinite(frac), np.nan_to_num(frac) >= 0.5
    elif kind == "fire":
        perims = fetch.perimeters(site)
        if not perims:
            raise ValueError("no fire reference perimeters available for this site")
        known = np.ones(grid.shape, dtype=bool)
        pos = refs_scoring.nifc_mask(grid, perims) if perims else np.zeros(grid.shape, bool)
    elif kind == "flood":
        d0, d1 = (_day(d) for d in site["meta"]["pair_dates"])
        pre = np.asarray(fetch.dswx_water(grid, d0), dtype=float)
        post = np.asarray(fetch.dswx_water(grid, d1), dtype=float)
        wet = np.nan_to_num(post) >= 0.5
        pos = wet & (np.nan_to_num(pre, nan=1.0) < 0.2)
        known = np.isfinite(post) & ~(wet & ~np.isfinite(pre))
    elif kind == "crops":
        frac = np.asarray(fetch.cdl_fraction(grid), dtype=float)
        known, pos = np.isfinite(frac), np.nan_to_num(frac) >= 0.5
    else:
        raise ValueError(f"unknown site kind {kind!r}")
    out[known] = "none"
    out[known & pos] = cls
    return out


# --- p-values and the default operating point ---------------------------------------------------


def neg_log10(p) -> np.ndarray:
    """-log10 p, capped at `NLP_CAP`; NaN stays NaN."""
    p = np.asarray(p, dtype=float)
    return np.minimum(-np.log10(np.clip(p, 10.0**-NLP_CAP, 1.0)), NLP_CAP) + 0.0 * p


def fisher_p(p_l, p_c) -> np.ndarray:
    """Fisher's method: -2 (ln p_L + ln p_C) ~ chi2 with 4 df if the two tests are independent.
    Where one p is NaN the other band's p is returned; both NaN gives NaN."""
    a, b = np.asarray(p_l, dtype=float), np.asarray(p_c, dtype=float)
    both = np.isfinite(a) & np.isfinite(b)
    stat = -2.0 * (np.log(np.clip(a, 1e-300, 1.0)) + np.log(np.clip(b, 1e-300, 1.0)))
    fused = special.chdtrc(4, np.where(both, stat, 0.0))
    return np.where(both, fused, np.where(np.isfinite(a), a, b))


def bonferroni_p(p_l, p_c) -> np.ndarray:
    """min(1, 2 min(p_L, p_C)): valid however the two bands co-vary (Ruling R12). With one band
    missing it is that band's own p."""
    a, b = np.asarray(p_l, dtype=float), np.asarray(p_c, dtype=float)
    both = np.isfinite(a) & np.isfinite(b)
    fused = np.minimum(1.0, 2.0 * np.fmin(a, b))
    return np.where(both, fused, np.where(np.isfinite(a), a, b))


def pvalue(df: pd.DataFrame, det: str) -> np.ndarray:
    """The p-value of a p-based detector as an array."""
    if det in _P_COL:
        return df[_P_COL[det]].to_numpy(dtype=float)
    if det == "fused_fisher":
        return fisher_p(df["p_L"], df["p_C"])
    if det == "fused_bonferroni":
        return bonferroni_p(df["p_L"], df["p_C"])
    raise ValueError(f"{det!r} has no p-value")


def effect(df: pd.DataFrame, det: str) -> np.ndarray:
    """Largest |relative change| over the detector's polarisations (NaN where none is finite)."""
    suffix = "30" if det == "L30" and "rel_HH30" in df else ""
    cols = np.stack([np.abs(df[f"rel_{p}{suffix}"].to_numpy(dtype=float))
                     for p in BAND_POLS[det]])
    with np.errstate(all="ignore"):
        return np.fmax.reduce(cols)


def flags(df: pd.DataFrame, det: str, q: float = Q, min_db: float = MIN_DB) -> pd.Series:
    """The default operating point: BH-FDR at `q` inside each site's box AND |effect| >= `min_db`."""
    p, gate = pvalue(df, det), effect(df, det) >= min_db
    out = np.zeros(len(df), dtype=bool)
    groups = df.groupby("site", sort=False).indices if "site" in df else {0: np.arange(len(df))}
    for idx in groups.values():
        out[idx] = detect.bh_fdr(p[idx], q)
    return pd.Series(out & gate, index=df.index)


def metrics(df: pd.DataFrame, band: str, min_db: float = MIN_DB, q: float = Q) -> dict:
    """Precision, recall, F1 at the default operating point, with the counts behind them.

    Uses the column `flag_<band>` when the table has it (needed for the trained detectors),
    otherwise `flags()`. Precision and recall are 0.0 (not NaN) when nothing is flagged.
    """
    col = f"flag_{band}"
    flag = df[col].to_numpy(bool) if col in df else flags(df, band, q, min_db).to_numpy()
    y = df["y"].to_numpy(bool)
    tp, n_flags, n_ref = int((flag & y).sum()), int(flag.sum()), int(y.sum())
    precision = tp / n_flags if n_flags else 0.0
    recall = tp / n_ref if n_ref else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "n_flags": n_flags,
            "n_ref": n_ref}


# --- rank-based curves --------------------------------------------------------------------------


def _sweep(score, y):
    """(recall, precision, threshold) at the end of every group of tied scores, best first."""
    score, y = np.asarray(score, dtype=float), np.asarray(y, dtype=bool)
    keep = np.isfinite(score)
    score, y = score[keep], y[keep]
    n_pos = int(y.sum())
    if n_pos == 0:
        return np.array([]), np.array([]), np.array([])
    order = np.argsort(-score, kind="stable")
    s, hit = score[order], y[order]
    tp, fp = np.cumsum(hit), np.cumsum(~hit)
    end = np.r_[s[1:] != s[:-1], True]  # tied scores are one threshold, not an arbitrary order
    tp, fp = tp[end], fp[end]
    return tp / n_pos, tp / (tp + fp), s[end]


def average_precision(score, y) -> float:
    """Area under the precision-recall curve of a threshold sweep over `score` (NaN: no positives)."""
    recall, precision, _ = _sweep(score, y)
    if recall.size == 0:
        return float("nan")
    return float(np.sum(np.diff(np.r_[0.0, recall]) * precision))


def pr_curve(df: pd.DataFrame, band: str) -> list[tuple[float, float, float]]:
    """[(recall, precision, threshold)] sweeping a threshold over the rank score `s_<band>`
    (recall rises as the threshold falls and ends at 1.0)."""
    recall, precision, thr = _sweep(df[f"s_{band}"], df["y"])
    return [(float(r), float(p), float(t)) for r, p, t in zip(recall, precision, thr)]


def auprc(curve) -> float:
    """Area under a `pr_curve`, summed the same way as `average_precision`."""
    r = np.array([c[0] for c in curve])
    p = np.array([c[1] for c in curve])
    return float(np.sum(np.diff(np.r_[0.0, r]) * p)) if r.size else float("nan")


def _precision_at(curve, recall: float) -> float:
    if not curve:
        return float("nan")
    r = np.array([c[0] for c in curve])
    p = np.array([c[1] for c in curve])
    uniq = np.unique(r)
    best = np.array([p[r == u].max() for u in uniq])  # best precision at each recall level
    return float(np.interp(recall, uniq, best))


def at_equal_recall(curve_a, curve_b, recall: float) -> tuple[float, float]:
    """Precision of each curve at the same recall (linear interpolation between curve points)."""
    return _precision_at(curve_a, recall), _precision_at(curve_b, recall)


# --- bootstraps over sites ----------------------------------------------------------------------


def _resampler(df: pd.DataFrame, by: str, seed: int):
    groups = list(df.groupby(by, sort=False).indices.values())
    rng = np.random.default_rng(seed)

    def draw() -> pd.DataFrame:
        pick = rng.integers(0, len(groups), len(groups))
        return df.iloc[np.concatenate([groups[i] for i in pick])]

    return draw


def bootstrap_ci(df: pd.DataFrame, fn, n: int = 500, by: str = "site", seed: int = 0,
                 alpha: float = 0.05) -> tuple[float, float]:
    """Percentile CI of `fn(df)` when whole sites (`by`) are resampled with replacement.
    Blocks inside one box are strongly dependent, so the site is the unit of replication."""
    draw = _resampler(df, by, seed)
    vals = np.array([fn(draw()) for _ in range(n)], dtype=float)
    lo, hi = np.nanpercentile(vals, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(lo), float(hi)


def paired_bootstrap_delta(df: pd.DataFrame, det_a: str, det_b: str, metric, n: int = 1000,
                           by: str = "site", seed: int = 0, alpha: float = 0.05) -> dict:
    """metric(det_b) - metric(det_a) on the same resampled sites, so shared difficulty cancels.

    `metric(df, det) -> float`. Returns the point delta, its percentile CI and `p_gt0`, the share
    of resamples where det_b beat det_a.
    """
    draw = _resampler(df, by, seed)
    deltas = np.empty(n)
    for i in range(n):
        d = draw()
        deltas[i] = metric(d, det_b) - metric(d, det_a)
    finite = deltas[np.isfinite(deltas)]
    if not finite.size:
        return {"delta": float(metric(df, det_b) - metric(df, det_a)), "ci_low": float("nan"),
                "ci_high": float("nan"), "p_gt0": float("nan"), "n_valid_draws": 0}
    lo, hi = np.nanpercentile(deltas, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return {"delta": float(metric(df, det_b) - metric(df, det_a)), "ci_low": float(lo),
            "ci_high": float(hi), "p_gt0": float(np.mean(finite > 0)),
            "n_valid_draws": int(finite.size)}


# --- the geographic split -----------------------------------------------------------------------


def choose_holdout_states(sites, seed: int = 20261114, frac: float = 0.3,
                          min_kind_frac: float = 0.2, flood_states=("IN", "AL")) -> list[str]:
    """States held out of training. Fixed seed, decided from the site list alone (never from
    results): one of `flood_states` first (the flood sites live there), then seeded random states
    until every kind has at least `min_kind_frac` of its sites held out and about `frac` of all
    sites are."""
    rng = np.random.default_rng(seed)
    kinds = sorted({s["kind"] for s in sites})
    total = Counter(s["kind"] for s in sites)
    need = {k: max(1, math.ceil(min_kind_frac * total[k])) for k in kinds}
    by_state: dict[str, Counter] = {}
    for s in sites:
        by_state.setdefault(s["state"], Counter())[s["kind"]] += 1
    held: list[str] = []
    forced = [st for st in flood_states if st in by_state and by_state[st]["flood"]]
    if forced:
        held.append(forced[int(rng.integers(len(forced)))])

    def counts() -> Counter:
        c: Counter = Counter()
        for st in held:
            c.update(by_state[st])
        return c

    for st in rng.permutation(sorted(by_state)):
        have = counts()
        unmet = [k for k in kinds if have[k] < need[k]]
        if not unmet and sum(have.values()) >= frac * len(sites):
            break
        if st not in held and (any(by_state[st][k] for k in unmet) or not unmet):
            held.append(str(st))
    have = counts()
    if any(have[k] < need[k] for k in kinds):
        raise ValueError("could not give every site kind a holdout share")
    return sorted(held)


def assign_split(sites, holdout_states) -> list[dict]:
    """Copies of `sites` with `split` = "holdout" when the state is held out, else "train"."""
    held = set(holdout_states)
    return [{**s, "split": "holdout" if s["state"] in held else "train"} for s in sites]


# --- logistic fusion ----------------------------------------------------------------------------

_POLS = {"L": ("HH", "HV"), "C": ("VV", "VH")}


def _design(df: pd.DataFrame, features: list[str]) -> np.ndarray:
    cols = []
    for f in features:
        kind, name = f.split("_", 1)
        if kind == "rel":
            cols.append(df[f].to_numpy(dtype=float))
        elif kind == "abs":
            cols.append(np.abs(df[f"rel_{name}"].to_numpy(dtype=float)))
        else:  # nlp_L / nlp_C
            cols.append(neg_log10(df[f"p_{name}"].to_numpy(dtype=float)))
    return np.stack(cols, axis=1)


def _fit_irls(x, y, w, l2: float, iters: int = 60) -> np.ndarray:
    xb = np.c_[np.ones(len(x)), x]
    beta = np.zeros(xb.shape[1])
    reg = l2 * np.eye(xb.shape[1])
    reg[0, 0] = 0.0
    for _ in range(iters):
        p = special.expit(xb @ beta)
        grad = xb.T @ (w * (y - p)) - reg @ beta
        hess = (xb * (w * p * (1 - p))[:, None]).T @ xb + reg + 1e-9 * np.eye(xb.shape[1])
        step = np.linalg.solve(hess, grad)
        beta += step
        if np.max(np.abs(step)) < 1e-7:
            break
    return beta


@dataclass
class FusionModel:
    """Ridge logistic regression on relative changes (signed and absolute) and -log10 p.

    `sensors` says which sensors' columns it may read: "both" is the fusion model, "L" and "C"
    are the one-sensor controls. `threshold` is the probability that gives at most `fa_target`
    false alarms on the training stable-ground blocks (0.5 when there were none)."""

    features: list[str]
    mean_: np.ndarray
    scale_: np.ndarray
    coef_: np.ndarray
    intercept_: float
    threshold: float = 0.5
    sensors: str = "both"

    def score(self, df: pd.DataFrame) -> np.ndarray:
        """The logit (a rank score); NaN where a feature is missing."""
        z = (_design(df, self.features) - self.mean_) / self.scale_
        return z @ self.coef_ + self.intercept_

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        return special.expit(self.score(df))


def fit_logistic_fusion(train_df: pd.DataFrame, sensors: str = "both", fa_target: float = 0.01,
                        l2: float = 1.0) -> FusionModel:
    """Fit on training-state rows only (`y` is the target; a `split` column, if present, must
    not say "holdout"). Classes are weighted equally. Rows with a missing feature are dropped."""
    if "split" not in train_df or not (train_df["split"] == "train").all():
        raise ValueError("fit_logistic_fusion got holdout-state rows: fit on training states only")
    if sensors not in ("both", "L", "C"):
        raise ValueError("sensors must be both, L or C")
    pols = [p for s in ("L", "C") if sensors in ("both", s) for p in _POLS[s]]
    sens = [s for s in ("L", "C") if sensors in ("both", s)]
    features = [f"rel_{p}" for p in pols] + [f"abs_{p}" for p in pols] + [f"nlp_{s}" for s in sens]
    x = _design(train_df, features)
    y = train_df["y"].to_numpy(bool)
    ok = np.isfinite(x).all(axis=1)
    x, y = x[ok], y[ok]
    if y.sum() == 0 or y.all():
        raise ValueError("fit_logistic_fusion needs both positive and negative training blocks")
    mean, scale = x.mean(axis=0), np.maximum(x.std(axis=0), 1e-9)
    w = np.where(y, 0.5 / y.mean(), 0.5 / (1 - y.mean()))  # equal total weight per class
    beta = _fit_irls((x - mean) / scale, y.astype(float), w, l2)
    model = FusionModel(features, mean, scale, beta[1:], float(beta[0]), 0.5, sensors)
    if "label" in train_df:
        stable = train_df.loc[train_df["label"] == "stable"]
        prob = model.predict_proba(stable)
        prob = prob[np.isfinite(prob)]
        if prob.size:
            model.threshold = float(np.nextafter(np.quantile(prob, 1 - fa_target), 1.0))
    return model

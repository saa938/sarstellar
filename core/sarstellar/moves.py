"""SARstellar v2 moves: per-hectare features of a NISAR series, from radar alone.

A block's dance is its HH and HV (dB) on every pass. Features describe the shape of that dance
without any land-cover map, so a model trained on US reference sites can run anywhere NISAR
flies:

* scene offsets: the per-date median of all blocks is removed first (calibration drift and
  scene-wide wetting, the Shimmer, are not a local move); the offsets are kept as features;
* the step: the split that best separates "before" from "after" (a CUSUM-style search on
  HV + HH), with before/after levels and the size of the step in HH, HV and HH-HV;
* excursions: the largest rise and drop away from the block's own median, and whether the block
  came back (transient water moves vs permanent canopy loss);
* neighbourhood: how much of the surrounding 7 x 7 hectares took the same step (fires burn wide
  patches; clearcuts are smaller, sharp-edged ones).
"""

from __future__ import annotations

import numpy as np

MOVE_IDS = ["still", "fall", "scorch", "bounce", "vanish", "waltz", "shimmer", "melt"]
LABEL_TO_MOVE = {
    "forest_loss": "fall",
    "burn": "scorch",
    "flood_open_water": "vanish",
    "crop_cycle": "waltz",
    "stable": "still",
    "none": "still",
}

FEATURES_HH = ["pre_HH", "post_HH", "d_HH", "rise_HH", "drop_HH", "back_HH", "std_HH",
               "range_HH", "nbr_d_HH"]
FEATURES_HV = ["pre_HV", "post_HV", "d_HV", "rise_HV", "drop_HV", "back_HV", "std_HV",
               "range_HV", "nbr_d_HV", "nbr_frac_drop_HV"]
FEATURES_BOTH = ["pre_R", "post_R", "d_R", "step_strength", "n_dates"]
FEATURES = FEATURES_HH + FEATURES_HV + FEATURES_BOTH


def scene_offsets(cube: np.ndarray, ref: np.ndarray | None = None) -> np.ndarray:
    """Per-date calibration/weather shift, from the scene's steadiest hectares. cube: [T, ...].

    The shift is the per-date median of the 25% of blocks whose `ref` series (default: the cube
    itself) varies least over time, minus the median of those medians. Using the steadiest
    blocks (towns, mature woods) keeps a scene full of crops from cancelling its own waltz.
    """
    t = cube.shape[0]
    flat = cube.reshape(t, -1).astype("float32")
    r = flat if ref is None else ref.reshape(t, -1).astype("float32")
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        ok = np.isfinite(r).sum(0) >= max(3, t // 2)
        sd = np.nanstd(r, axis=0)
        cut = np.nanpercentile(sd[ok], 25) if ok.any() else np.inf
        steady = ok & (sd <= cut)
        if steady.sum() < 50:
            steady = ok
        med = np.array([np.nanmedian(row[steady]) if np.isfinite(row[steady]).any() else np.nan
                        for row in flat])
    return med - np.nanmedian(med)


def _box_mean(a: np.ndarray, k: int = 7) -> np.ndarray:
    """Mean over a k x k neighbourhood, ignoring NaN (edges use what exists)."""
    from scipy.ndimage import uniform_filter

    ok = np.isfinite(a)
    num = uniform_filter(np.where(ok, a, 0.0), size=k, mode="constant")
    den = uniform_filter(ok.astype("float64"), size=k, mode="constant")
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, np.nan)


def best_split(hh: np.ndarray, hv: np.ndarray) -> np.ndarray:
    """Index t (1..T-1) of the strongest before/after step per block. hh, hv: [T, N] (NaN ok)."""
    t_n, n = hh.shape
    sig = np.nan_to_num(hv, nan=np.nanmean(hv)) + 0.5 * np.nan_to_num(hh, nan=np.nanmean(hh))
    csum = np.cumsum(sig, axis=0)
    total = csum[-1]
    best = np.ones(n, dtype=int)
    best_val = np.full(n, -np.inf)
    for t in range(1, t_n):
        before = csum[t - 1] / t
        after = (total - csum[t - 1]) / (t_n - t)
        val = np.abs(after - before) * np.sqrt(t * (t_n - t) / t_n)
        upd = val > best_val
        best[upd], best_val[upd] = t, val[upd]
    return best


def block_features(hh: np.ndarray, hv: np.ndarray, shape: tuple[int, int]) -> dict:
    """Features for every block. hh, hv: [T, ny, nx] dB (NaN = no data); shape = (ny, nx).

    Returns a dict of 1-D arrays of length ny * nx (row-major), plus `split` (the step index)
    and `offset_HH` / `offset_HV` (the scene offsets per date, length T).
    """
    t_n = hh.shape[0]
    ny, nx = shape
    off_hh, off_hv = scene_offsets(hh, ref=hv), scene_offsets(hv, ref=hv)
    H = (hh.reshape(t_n, -1) - off_hh[:, None]).astype("float64")
    V = (hv.reshape(t_n, -1) - off_hv[:, None]).astype("float64")
    R = H - V
    n = H.shape[1]
    split = best_split(H, V)
    idx = np.arange(t_n)[:, None]
    before = idx < split[None, :]
    import warnings

    with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)

        def seg_mean(a, m):
            a2 = np.where(m & np.isfinite(a), a, np.nan)
            return np.nanmean(a2, axis=0)

        f: dict[str, np.ndarray] = {}
        for name, a in (("HH", H), ("HV", V), ("R", R)):
            pre, post = seg_mean(a, before), seg_mean(a, ~before)
            f[f"pre_{name}"], f[f"post_{name}"], f[f"d_{name}"] = pre, post, post - pre
        for name, a in (("HH", H), ("HV", V)):
            med = np.nanmedian(a, axis=0)
            f[f"rise_{name}"] = np.nanmax(a, axis=0) - med
            f[f"drop_{name}"] = np.nanmin(a, axis=0) - med
            last = a[-1]
            # how far the block came back from its largest excursion, in the excursion's direction
            exc = np.where(f[f"rise_{name}"] > -f[f"drop_{name}"], np.nanmax(a, axis=0),
                           np.nanmin(a, axis=0))
            f[f"back_{name}"] = np.abs(exc - last) - np.abs(exc - med)
            f[f"std_{name}"] = np.nanstd(a, axis=0)
            f[f"range_{name}"] = np.nanmax(a, axis=0) - np.nanmin(a, axis=0)
        f["step_strength"] = np.abs(f["d_HV"]) + 0.5 * np.abs(f["d_HH"])
        f["n_dates"] = np.isfinite(H).sum(axis=0).astype("float64")
        f["nbr_d_HH"] = _box_mean(f["d_HH"].reshape(ny, nx)).ravel()
        f["nbr_d_HV"] = _box_mean(f["d_HV"].reshape(ny, nx)).ravel()
        drop = np.where(np.isfinite(f["d_HV"]), (f["d_HV"] <= -2.0).astype("float64"), np.nan)
        f["nbr_frac_drop_HV"] = _box_mean(drop.reshape(ny, nx)).ravel()
    valid = np.isfinite(H).sum(axis=0) >= max(3, t_n // 2)
    valid &= np.isfinite(V).sum(axis=0) >= max(3, t_n // 2)
    for k in list(f):
        f[k] = np.where(valid, f[k], np.nan).astype("float32")
    f["valid"] = valid
    f["split"] = split.astype("int16")
    f["offset_HH"], f["offset_HV"] = off_hh.astype("float32"), off_hv.astype("float32")
    return f

"""Learn the moves from reference sites, measure them on held-out states, apply them to stages.

Supervised moves (labels from independent references, see scoring.block_labels):
  still (stable sites + blocks the reference says did not change), fall (DIST-ALERT-HLS forest
  loss), scorch (NIFC perimeters), vanish (DSWx open-water gain), waltz (CDL cultivated land).
Physics moves without labels are rules, applied after the model and reported as rules:
  bounce (HH rises >= 3 dB while HV holds, under vegetation), melt (HH-only ice stages).

Evaluation uses the scorecard's fixed geographic split (`split` == "holdout" states are never
used for fitting or selection) and a site bootstrap for intervals.
"""

from __future__ import annotations

import json
import warnings

import numpy as np
import pandas as pd

from .moves import FEATURES, FEATURES_BOTH, FEATURES_HH, FEATURES_HV, MOVE_IDS, block_features

CLASSES = ["still", "fall", "scorch", "vanish", "waltz"]
ABLATIONS = {
    "HH only": FEATURES_HH,
    "HV only": FEATURES_HV,
    "HH + HV": FEATURES,
}
# Two-pass model: the change in HH and HV between a before and an after pass (scene shift
# removed). Trained on the scorecard's 2.2M reference hectares, which store exactly that.
PAIR_FEATURES = ["d_HH", "d_HV", "d_R"]
PAIR_ABLATIONS = {
    "HH only": ["d_HH"],
    "HV only": ["d_HV"],
    "HH + HV": PAIR_FEATURES,
}


def pair_table(blocks: pd.DataFrame, max_still_per_site: int = 20000, seed: int = 20261115):
    """The scorecard block table -> training rows with d_HH, d_HV, d_R and a move label."""
    from .moves import LABEL_TO_MOVE

    t = blocks[blocks["valid"] & blocks["label"].isin(list(LABEL_TO_MOVE))].copy()
    t = t.dropna(subset=["rel_HH", "rel_HV"])
    t["d_HH"], t["d_HV"] = t["rel_HH"].astype("float32"), t["rel_HV"].astype("float32")
    t["d_R"] = t["d_HH"] - t["d_HV"]
    t["move"] = t["label"].map(LABEL_TO_MOVE)
    rng = np.random.default_rng(seed)
    parts = []
    for _, g in t.groupby("site", sort=False):
        still = g[g["move"] == "still"]
        if len(still) > max_still_per_site:
            still = still.iloc[rng.choice(len(still), max_still_per_site, replace=False)]
        parts.append(pd.concat([g[g["move"] != "still"], still]))
    return pd.concat(parts, ignore_index=True)[
        ["site", "state", "kind", "split", "label", "move", *PAIR_FEATURES]]


def _weights(y: np.ndarray) -> np.ndarray:
    counts = np.bincount(y, minlength=len(CLASSES)).astype(float)
    w = counts.sum() / np.maximum(counts, 1) / len(CLASSES)
    return w[y]


def fit(train: pd.DataFrame, feats: list[str], seed: int = 0):
    import lightgbm as lgb

    y = train["move"].map({c: i for i, c in enumerate(CLASSES)}).to_numpy()
    model = lgb.LGBMClassifier(
        objective="multiclass", num_class=len(CLASSES), n_estimators=500, learning_rate=0.05,
        num_leaves=63, min_child_samples=50, subsample=0.8, subsample_freq=1,
        colsample_bytree=0.9, reg_lambda=1.0, random_state=seed, n_jobs=-1, verbose=-1)
    model.fit(train[feats].to_numpy(np.float32), y, sample_weight=_weights(y))
    return model


def average_precision(y: np.ndarray, s: np.ndarray) -> float:
    if y.sum() == 0:
        return float("nan")
    order = np.argsort(-s, kind="mergesort")
    y = y[order]
    tp = np.cumsum(y)
    prec = tp / np.arange(1, len(y) + 1)
    return float((prec * y).sum() / y.sum())


def _metrics(y_true: np.ndarray, proba: np.ndarray) -> dict:
    pred = proba.argmax(1)
    out = {}
    for i, c in enumerate(CLASSES):
        t, p = y_true == i, pred == i
        tp = float((t & p).sum())
        prec = tp / max(p.sum(), 1)
        rec = tp / max(t.sum(), 1)
        out[c] = {"precision": prec, "recall": rec,
                  "f1": 2 * prec * rec / max(prec + rec, 1e-9),
                  "auprc": average_precision(t.astype(int), proba[:, i]),
                  "base_rate": float(t.mean()), "n": int(t.sum())}
    out["macro_f1_moves"] = float(np.mean([out[c]["f1"] for c in CLASSES[1:]]))
    return out


GATE_HV_DB, GATE_HH_DB = 2.5, 3.0


def gate(d_hh: np.ndarray, d_hv: np.ndarray) -> np.ndarray:
    """True where the radar changed enough to name a move (otherwise the hectare is still)."""
    return (np.abs(np.nan_to_num(d_hv)) >= GATE_HV_DB) | (np.abs(np.nan_to_num(d_hh)) >= GATE_HH_DB)


def gated_predict(proba: np.ndarray, d_hh: np.ndarray, d_hv: np.ndarray) -> np.ndarray:
    """Most likely non-still move where the gate passes, else still (class 0)."""
    move_best = 1 + proba[:, 1:].argmax(1)
    return np.where(gate(d_hh, d_hv), move_best, 0)


def gated_metrics(test: pd.DataFrame, proba: np.ndarray) -> dict:
    """Precision/recall per move for the labels the site actually shows (gated)."""
    y = test["move"].map({c: i for i, c in enumerate(CLASSES)}).to_numpy()
    pred = gated_predict(proba, test["d_HH"].to_numpy() if "d_HH" in test else np.zeros(len(test)),
                         test["d_HV"].to_numpy() if "d_HV" in test else np.zeros(len(test)))
    out = {}
    for i, c in enumerate(CLASSES):
        t, p = y == i, pred == i
        tp = float((t & p).sum())
        prec, rec = tp / max(p.sum(), 1), tp / max(t.sum(), 1)
        out[c] = {"precision": prec, "recall": rec, "f1": 2 * prec * rec / max(prec + rec, 1e-9),
                  "n_flagged": int(p.sum()), "base_rate": float(t.mean())}
    changed = pred != 0
    truly = y != 0
    out["any_move"] = {"precision": float((changed & truly).sum() / max(changed.sum(), 1)),
                       "recall": float((changed & truly).sum() / max(truly.sum(), 1)),
                       "base_rate": float(truly.mean())}
    out["gate"] = {"hv_db": GATE_HV_DB, "hh_db": GATE_HH_DB}
    return out


def evaluate(table: pd.DataFrame, feats: list[str], n_boot: int = 300, seed: int = 20261115):
    train = table[table["split"] == "train"]
    test = table[table["split"] == "holdout"].reset_index(drop=True)
    model = fit(train, feats)
    proba = model.predict_proba(test[feats].to_numpy(np.float32))
    y = test["move"].map({c: i for i, c in enumerate(CLASSES)}).to_numpy()
    point = _metrics(y, proba)
    point["gated"] = gated_metrics(test, proba)
    # site bootstrap
    rng = np.random.default_rng(seed)
    sites = test["site"].to_numpy()
    uniq = np.unique(sites)
    idx_by_site = {s: np.flatnonzero(sites == s) for s in uniq}
    draws = {c: {"f1": [], "auprc": []} for c in CLASSES}
    draws["macro_f1_moves"] = []
    for _ in range(n_boot):
        pick = rng.choice(uniq, len(uniq), replace=True)
        ii = np.concatenate([idx_by_site[s] for s in pick])
        m = _metrics(y[ii], proba[ii])
        for c in CLASSES:
            draws[c]["f1"].append(m[c]["f1"])
            draws[c]["auprc"].append(m[c]["auprc"])
        draws["macro_f1_moves"].append(m["macro_f1_moves"])
    for c in CLASSES:
        for k in ("f1", "auprc"):
            v = np.array(draws[c][k], dtype=float)
            v = v[np.isfinite(v)]
            point[c][f"{k}_ci"] = ([float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]
                                   if v.size else None)
    v = np.array(draws["macro_f1_moves"])
    point["macro_f1_moves_ci"] = [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]
    conf = np.zeros((len(CLASSES), len(CLASSES)), dtype=int)
    np.add.at(conf, (y, proba.argmax(1)), 1)
    point["confusion"] = {"classes": CLASSES, "rows_true_cols_pred": conf.tolist()}
    point["n_test_sites"] = int(len(uniq))
    point["n_test_states"] = int(test["state"].nunique())
    point["n_test_blocks"] = int(len(test))
    point["n_train_sites"] = int(train["site"].nunique())
    point["n_train_blocks"] = int(len(train))
    return model, point


def run_all(table: pd.DataFrame, n_boot: int = 300, ablations: dict | None = None
            ) -> tuple[object, dict]:
    """Main model + polarization ablations. Returns (main model, report dict)."""
    ablations = ablations or ABLATIONS
    report = {"classes": CLASSES, "features": ablations["HH + HV"], "ablations": {}}
    model = None
    for name, feats in ablations.items():
        m, r = evaluate(table, feats, n_boot=n_boot)
        report["ablations"][name] = r
        if name == "HH + HV":
            model = m
            report["main"] = r
            imp = dict(zip(feats, m.booster_.feature_importance("gain").tolist()))
            report["importance_gain"] = dict(sorted(imp.items(), key=lambda kv: -kv[1]))
    counts = table.groupby(["split", "move"]).size().unstack(fill_value=0)
    report["counts"] = json.loads(counts.to_json())
    return model, report


# --- applying the moves to a stage ------------------------------------------------------------


def apply_to_stage(model, cube: dict, feats: list[str] | None = None) -> dict:
    """Per-block move + confidence and per-beat moves for one stage cube.

    cube: {"blocks_HH": [T, ny, nx], "blocks_HV"?: [T, ny, nx]} in dB.
    """
    hh = cube["blocks_HH"].astype("float32")
    t_n, ny, nx = hh.shape
    n = ny * nx
    idx = {m: i for i, m in enumerate(MOVE_IDS)}
    move = np.full(n, 255, dtype="uint8")
    conf = np.zeros(n, dtype="uint8")
    beat = np.full((t_n, n), 255, dtype="uint8")
    H = hh.reshape(t_n, n)
    with np.errstate(invalid="ignore"):
        medH = np.nanmedian(H, axis=0)
    if "blocks_HV" not in cube:  # ice: one channel, rules only
        valid = np.isfinite(H).sum(0) >= max(3, t_n // 2)
        dev = H - medH
        rng_h = np.nanmax(H, 0) - np.nanmin(H, 0)
        is_melt = valid & (rng_h >= 4.0)
        move[valid] = idx["still"]
        move[is_melt] = idx["melt"]
        conf[valid] = 100
        beat[:, valid] = idx["still"]
        # the ice surface swings both ways through the melt season (wet snow absorbs, rough bare
        # ice and refrozen crust scatter): a melt beat is any >= 3 dB departure from normal
        beat[(np.abs(dev) >= 3.0) & is_melt[None, :]] = idx["melt"]
        return {"move": move, "conf": conf, "beat_move": beat, "split": None,
                "features": None}
    hv = cube["blocks_HV"].astype("float32")
    f = block_features(hh, hv, (ny, nx))
    valid = f["valid"]
    feats = feats or FEATURES
    X = np.stack([f[k] for k in feats], axis=1)[valid]
    proba = model.predict_proba(X.astype(np.float32))
    cls = gated_predict(proba, f["d_HH"][valid], f["d_HV"][valid])
    move[valid] = np.array([idx[CLASSES[c]] for c in cls], dtype="uint8")
    # confidence: the chosen class's share of the probability among the moves (or still's)
    moves_p = proba[:, 1:] / np.maximum(proba[:, 1:].sum(1, keepdims=True), 1e-9)
    conf_moving = moves_p.max(1)
    conf[valid] = np.round(np.where(cls == 0, proba[:, 0], conf_moving) * 100).astype("uint8")
    # Context the two-pass model cannot see, from the hectare's whole series on the floor:
    #  * water: a land hectare that went dark in both channels on some pass is a Vanish
    #    (HH <= -18 dB and HV <= -24 dB: calm open water at L-band); permanent water stays still;
    #  * canopy loss (Fall/Scorch) needs a forest before the step (HV never near bare soil) and
    #    HH not rising; HV falling while HH rises is water under vegetation (a Bounce);
    #  * a field that loses HV after a bare-soil phase is a harvest: the end of a Waltz;
    #  * Fall vs Scorch by patch size: fires burn thousands of connected hectares, cuts tens.
    from scipy.ndimage import label as _label

    Hn0 = H - f["offset_HH"][:, None]
    Vn0 = hv.reshape(t_n, n) - f["offset_HV"][:, None]
    tt0 = np.arange(t_n)[:, None]
    before0 = tt0 < f["split"].astype(int)[None, :]
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        dark = ((Hn0 <= -18.0) & (Vn0 <= -24.0)).any(0)
        med_hh = np.nanmedian(Hn0, 0)
        hv_before_low = np.nanpercentile(np.where(before0, Vn0, np.nan), 10, axis=0)
        hv_min = np.nanmin(Vn0, 0)
    is_land = med_hh > -16.0
    went_dark = dark & is_land
    forest_before = hv_before_low >= -16.5
    canopy_loss = np.isin(move, [idx["fall"], idx["scorch"]])
    rng_hv = f["range_HV"]
    # water first
    move[went_dark & valid & (move != idx["still"]) | (went_dark & valid & (f["drop_HH"] <= -3.0))] = idx["vanish"]
    move[(move == idx["vanish"]) & ~went_dark] = idx["still"]
    # canopy loss needs a forest before and HH not rising
    cl = canopy_loss & ~went_dark
    move[cl & forest_before & (f["d_HH"] >= 1.5)] = idx["bounce"]
    harvest = cl & ~forest_before
    move[harvest & (rng_hv >= 3.0)] = idx["waltz"]
    move[harvest & ~(rng_hv >= 3.0)] = idx["still"]
    # waltz needs a real season: a big HV range and a bare-ish phase
    move[(move == idx["waltz"]) & ~((rng_hv >= 3.0) & (hv_min <= -17.0))] = idx["still"]
    # fall vs scorch by burn-scale patch size: join fragments within ~300 m first
    from scipy.ndimage import binary_closing as _closing

    loss = np.isin(move, [idx["fall"], idx["scorch"]]).reshape(ny, nx)
    joined = _closing(loss, structure=np.ones((7, 7)))
    lab, nlab = _label(joined, structure=np.ones((3, 3)))
    if nlab:
        sizes = np.bincount(lab.ravel())
        big = (sizes[lab] >= 1500).ravel() & loss.ravel()
        move[loss.ravel() & big] = idx["scorch"]
        move[loss.ravel() & ~big] = idx["fall"]
    move[~valid] = 255
    # per-beat moves from the physics of each pass relative to the block's own baseline
    Hn = H - f["offset_HH"][:, None]
    V = hv.reshape(t_n, n) - f["offset_HV"][:, None]
    with np.errstate(invalid="ignore"):
        dH = Hn - np.nanmedian(Hn, 0)
        dV = V - np.nanmedian(V, 0)
        lowV = V - np.nanpercentile(V, 20, axis=0)
    tt = np.arange(t_n)[:, None]
    beat[:, valid] = idx["still"]
    grow = (lowV >= 2.5) & (dV >= 1.0)
    beat[grow] = idx["waltz"]
    bnc = (dH >= 2.5) & ((dH - dV) >= 2.0)
    beat[bnc] = idx["bounce"]
    van = (dH <= -3.0) & (dV <= -2.5)
    beat[van] = idx["vanish"]
    after = tt >= f["split"].astype(int)[None, :]
    for m in ("fall", "scorch"):
        sel = move == idx[m]
        beat[after & sel[None, :]] = idx[m]
    beat[:, ~valid] = 255
    # physics rule at block level: the Bounce (HH-led rises on several passes), unlabeled in the
    # reference set, overrides "still", "vanish" and "waltz"
    n_bounce = (beat == idx["bounce"]).sum(0)
    take = valid & (n_bounce >= 2) & np.isin(move, [idx["still"], idx["vanish"], idx["waltz"]])
    take &= (f["rise_HH"] - np.maximum(f["rise_HV"], 0)) >= 2.0
    move[take] = idx["bounce"]
    conf[take] = np.clip(np.round(50 + 8 * (f["rise_HH"][take] - 2.5)), 50, 95).astype("uint8")
    return {"move": move, "conf": conf, "beat_move": beat, "split": f["split"], "features": f}


def pick_highlights(result: dict, cube: dict, headline: str, k: int = 6) -> list[int]:
    """A few spatially spread, confident blocks doing the stage's headline move."""
    idx = MOVE_IDS.index(headline)
    move, conf = result["move"], result["conf"]
    hh = cube["blocks_HH"]
    t_n, ny, nx = hh.shape
    f = result.get("features")
    if f is None:
        H = hh.reshape(t_n, -1).astype("float32")
        strength = np.nan_to_num(np.nanmax(H, 0) - np.nanmin(H, 0))
    else:
        key = {"fall": "step_strength", "scorch": "step_strength", "waltz": "range_HV",
               "bounce": "rise_HH", "vanish": "drop_HH"}.get(headline, "step_strength")
        strength = np.nan_to_num(f[key])
        if headline == "vanish":
            strength = -strength
    score = np.where(move == idx, strength * (conf / 100.0), -np.inf)
    order = np.argsort(-score)
    picked: list[int] = []
    for b in order[:5000]:
        if not np.isfinite(score[b]):
            break
        r, c = divmod(int(b), nx)
        if all(abs(r - pr) + abs(c - pc) > max(ny, nx) // 8 for pr, pc in
               (divmod(p, nx) for p in picked)):
            picked.append(int(b))
        if len(picked) >= k:
            break
    return picked

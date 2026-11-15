"""Held-out scorecard report; all fitting and detector selection use training states."""

from __future__ import annotations

import hashlib
import importlib
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

import numpy as np
import pandas as pd

from sarstellar import scoring
from sarstellar.scoring_bootstrap import bootstrap_ap, paired_ap_delta

DETECTORS = ("L", "C", "L30", "fused_fisher", "fused_bonferroni", "fused_logistic")


def code_provenance() -> dict:
    """Portable hashes of normalized source text plus the runtime's numerical library versions."""
    modules = ("sarstellar.features", "sarstellar.detect", "sarstellar.read", "sarstellar.grid",
               "sarstellar.search", "sarstellar.refs", "sarstellar.refs_scoring",
               "sarstellar.scoring", "sarstellar.scoring_bootstrap",
               "modal_app.scorecard_data", "modal_app.scorecard_paths", "modal_app.scorecard_report")
    files = {}
    for name in sorted(modules):
        path = Path(importlib.import_module(name).__file__)
        files[name] = hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest()
    source = "".join(f"{name}:{digest}\n" for name, digest in files.items())
    libraries = ("numpy", "scipy", "pandas", "rasterio", "h5py", "pyproj", "earthaccess",
                 "fsspec", "shapely", "pyarrow")
    return {"source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "source_files": files,
            "dependencies": {name: metadata.version(name) for name in libraries}}


def _ap(frame, det):
    return scoring.average_precision(frame[f"s_{det}"], frame["y"])


def _clean(value):
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    return value


def build_report(table: pd.DataFrame, sites: list[dict], *, failures=None,
                 n_boot=500, seed=20261114) -> dict:
    """Evaluate the same blocks for every primary detector. CI bars describe AUPRC.

    A single binary logistic model predicts any independently mapped change. It is fitted on
    training states only. Per class, the better single sensor and fusion method are selected
    on training AUPRC, then frozen for the held-out paired bootstrap.
    """
    report = {
        "generated_at": datetime.now(UTC).isoformat(), "fixture": False,
        "n_sites": 0, "n_processed_sites": int(table.site.nunique()) if len(table) else 0,
        "n_attempted": len(sites), "operating_point": {"q": scoring.Q, "min_db": scoring.MIN_DB},
        "holdout_states": sorted({s["state"] for s in sites if s["split"] == "holdout"}),
        "sites": [{k: s[k] for k in ("id", "kind", "bbox", "state", "split")} for s in sites],
        "classes": [], "equal_recall": [], "fusion": [], "stable_fa": {}, "model": None,
        "failed_sites": failures or [], "excluded_sites": [],
        "extra_detectors": [], "learned_fusion": [],
        "provenance": code_provenance(),
        "bootstrap": {"n_draws": n_boot, "seed": seed, "unit": "site", "confidence": 0.95},
        "notes": (
            "Two dates per primary radar, pinned to each site's catalogued pair. Primary metrics "
            "use identical blocks with valid L, C, L30 and reference data; missing C is excluded. "
            "Geographic split fixed before processing; fitting and detector selection use training "
            "states only. Site bootstrap, 95% percentile intervals, shown for AUPRC. Stable false "
            "alarms use held-out stable sites only, not negatives in selected disturbance sites. "
            "Forest/fire/flood sites were selected for reference positives; this is not a random "
            "national prevalence survey. Crop labels mean cultivated land, not confirmed crop "
            "change. Per-class rows measure change detection within sites selected for that kind "
            "plus stable controls, not multiclass cause-label accuracy. Land-cover strata with "
            "at least two sites and 20 reference positives are reported alongside pooled rows. "
            "DSWx-S1 references use Sentinel-1 and are not sensor-independent flood truth. "
            "Fisher fusion assumes independence; Bonferroni is also reported. Logistic threshold "
            "is calibrated on training stable blocks, not a p-value or BH-FDR threshold. L_series "
            "uses more NISAR dates and is reported separately from the headline. The primary "
            "fusion headline compares unsupervised Fisher/Bonferroni with raw L/C. Supervised "
            "logistic fusion is compared separately against equally trained single-sensor controls."
        ),
    }
    success = set(table.site.unique()) if len(table) else set()
    counts = table.groupby("site").comparable.agg(["size", "sum"]) if len(table) else None
    for s in report["sites"]:
        s["status"] = "done" if s["id"] in success else "error"
        if s["id"] in success:
            s["n_blocks"] = int(counts.loc[s["id"], "size"])
            s["n_comparable_blocks"] = int(counts.loc[s["id"], "sum"])
            if not s["n_comparable_blocks"]:
                s["status"] = "excluded"
                report["excluded_sites"].append({
                    "id": s["id"], "reason": "No common valid paired L/C/L30 and reference blocks"})
    # Legacy web consumers count sites[] directly; expose the evaluated cohort there and
    # keep the full fixed split plus per-site outcomes as additive audit fields.
    report["attempted_sites"] = report["sites"]
    report["sites"] = [s for s in report["attempted_sites"] if s["status"] == "done"]
    report["planned_holdout_states"] = report["holdout_states"]
    report["holdout_states"] = sorted({s["state"] for s in report["sites"]
                                       if s["split"] == "holdout"})
    report["n_sites"] = len(report["sites"])
    report["n_comparable_sites"] = report["n_sites"]
    if table.empty:
        report["status"] = "incomplete"
        return report
    frame = table.loc[table.comparable].copy()
    report["n_comparable_sites"] = int(frame.site.nunique())
    report["n_comparable_blocks"] = len(frame)
    report["adequacy"] = {"minimum_comparable_sites": 150,
                          "meets_site_target": frame.site.nunique() >= 150}
    train = frame.loc[frame.split.eq("train")]
    report["n_train_sites"] = int(train.site.nunique())
    report["n_holdout_sites"] = int(frame.loc[frame.split.eq("holdout")].site.nunique())
    detectors = list(DETECTORS)
    try:
        model = scoring.fit_logistic_fusion(train)
        frame["s_fused_logistic"] = model.score(frame)
        frame["flag_fused_logistic"] = model.predict_proba(frame) >= model.threshold
        report["fusion_model"] = {"features": model.features, "threshold": model.threshold,
                                  "training_sites": int(train.site.nunique())}
        for sensor in ("L", "C"):
            control = scoring.fit_logistic_fusion(train, sensors=sensor)
            frame[f"s_learned_{sensor}"] = control.score(frame)
    except ValueError as exc:
        detectors.remove("fused_logistic")
        report["fusion_model_error"] = str(exc)
    train = frame.loc[frame.split.eq("train")]
    held = frame.loc[frame.split.eq("holdout")]
    stable = held.loc[held.kind.eq("stable")]
    report["stable_fa"] = {
        det: float(stable[f"flag_{det}"].mean()) if len(stable) else None for det in detectors
    }
    for kind, cls in scoring.KIND_CLASS.items():
        subset = held.loc[held.kind.isin([kind, "stable"])].copy()
        fitting = train.loc[train.kind.isin([kind, "stable"])].copy()
        subset["y"], fitting["y"] = subset.label.eq(cls), fitting.label.eq(cls)
        if not subset.y.any() or not fitting.y.any():
            continue
        curves = {}
        for det in detectors:
            curve = scoring.pr_curve(subset, det)
            curves[det] = curve
            lo, hi = bootstrap_ap(subset, det, n=n_boot, seed=seed)
            report["classes"].append({"class": cls, "landcover": "all", "detector": det,
                                       **scoring.metrics(subset, det), "auprc": scoring.auprc(curve),
                                       "ci_low": lo, "ci_high": hi,
                                       "n_sites": int(subset.site.nunique())})
        for landcover, stratum in subset.groupby("landcover", sort=True):
            if not landcover or stratum.site.nunique() < 2 or stratum.y.sum() < 20:
                continue
            for det in detectors:
                lo, hi = bootstrap_ap(stratum, det, n=n_boot, seed=seed)
                report["classes"].append({"class": cls, "landcover": str(landcover),
                                           "detector": det, **scoring.metrics(stratum, det),
                                           "auprc": _ap(stratum, det), "ci_low": lo,
                                           "ci_high": hi, "n_sites": int(stratum.site.nunique())})
        recall = 0.5
        pl, pc = scoring.at_equal_recall(curves["L"], curves["C"], recall)
        pl30 = scoring.at_equal_recall(curves["L"], curves["L30"], recall)[1]
        report["equal_recall"].append({"class": cls, "recall": recall, "precision_L": pl,
                                       "precision_C": pc, "precision_L30": pl30,
                                       "ratio_L_over_C": pl / pc if pc > 0 else None})
        best = max(("L", "C"), key=lambda d: _ap(fitting, d))
        fused = max(("fused_fisher", "fused_bonferroni"),
                    key=lambda d: _ap(fitting, d))
        delta = paired_ap_delta(subset, best, fused, n=n_boot, seed=seed)
        report["fusion"].append({"class": cls, "best_single": best, "fused": fused,
                                  "metric": "auprc", "selection_split": "train", **delta})
        if "fused_logistic" in detectors:
            controls = ("learned_L", "learned_C")
            learned_best = max(controls, key=lambda d: _ap(fitting, d))
            learned_delta = paired_ap_delta(
                subset, learned_best, "fused_logistic", n=n_boot, seed=seed)
            report["learned_fusion"].append({
                "class": cls, "best_single": learned_best, "fused": "fused_logistic",
                "metric": "auprc", "selection_split": "train", **learned_delta,
                "auprc_L": _ap(subset, "learned_L"),
                "auprc_C": _ap(subset, "learned_C"),
                "auprc_fused": _ap(subset, "fused_logistic"),
            })
        extra = subset.loc[np.isfinite(subset.p_Ls)]
        if len(extra) and extra.y.any():
            report["extra_detectors"].append({"class": cls, "detector": "L_series",
                                               "auprc": _ap(extra, "L_series"),
                                               "n_sites": int(extra.site.nunique())})
    report["status"] = ("complete" if len(report["fusion"]) == len(scoring.KIND_CLASS)
                        and report["adequacy"]["meets_site_target"] else "incomplete")
    return _clean(report)

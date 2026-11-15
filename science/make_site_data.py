"""Build web/public/moves.json (field guide) and web/public/proof.json from measured outputs.

    python science/make_site_data.py --raw ../raw --web web/public --scorecard web/public/scorecard.json

Inputs (downloaded from the Modal Volume):
  <raw>/<stage>/cube.npz, moves.npz, refs.npz (optional), stage.json
  <raw>/_ref/moves_report.json      (held-out evaluation + polarization ablations)
  <raw>/_ref/run_stats.json         (counts of reads etc., optional)
Canonical move paths are medians over confident blocks of the stages that show each move.
"""

from __future__ import annotations

import argparse
import json
import warnings
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

warnings.simplefilter("ignore", RuntimeWarning)

MOVE_IDS = ["still", "fall", "scorch", "bounce", "vanish", "waltz", "shimmer", "melt"]

GUIDE = {
    "still": {
        "name": "The Stillness", "what": "Nothing changes on the ground.",
        "physics": "A surface that does not change returns the same echo pass after pass. The dot "
                   "only shivers inside the radar's speckle noise.",
        "carried_by": [], "future": "The baseline every alert is measured against: knowing what "
        "normal looks like is what makes a change trustworthy.",
    },
    "fall": {
        "name": "The Fall", "what": "A forest is cleared or logged.",
        "physics": "Leaves and branches scatter the radar in every direction, which is what HV "
                   "hears. Remove the canopy and HV drops several decibels in one pass; HH drops "
                   "less.",
        "carried_by": ["HV"], "future": "Deforestation alerts through the clouds of the tropical "
        "wet season, when optical satellites are blind for months.",
    },
    "scorch": {
        "name": "The Scorch", "what": "A wildfire burns.",
        "physics": "Burned forest loses its canopy, so HV falls like a clearcut, but over a wide, "
                   "connected patch. Grass and shrub fires barely register at L-band: its 24 cm "
                   "waves pass through thin vegetation.",
        "carried_by": ["HV", "HH"], "future": "Burn severity and recovery mapping under smoke and "
        "at night, for fire managers and insurers.",
    },
    "bounce": {
        "name": "The Bounce", "what": "Water stands under plants: flooded forest or rice paddies.",
        "physics": "The pulse bounces off the water, up the trunks or stems, and straight back to "
                   "the radar. HH jumps by several decibels while HV barely moves. L-band reaches "
                   "the water under a canopy; shorter radar waves cannot.",
        "carried_by": ["HH"], "future": "Mapping floods hidden under forest canopies, and tracking "
        "rice planting across Asia's paddies for food-security forecasts.",
    },
    "vanish": {
        "name": "The Vanish", "what": "Open water covers the land.",
        "physics": "Calm water is a mirror: the pulse reflects away and almost nothing comes back. "
                   "Both channels go dark. When the water drains, the dot returns.",
        "carried_by": ["HH", "HV"], "future": "Flood extent through storm clouds and at night, every "
        "12 days everywhere on Earth.",
    },
    "waltz": {
        "name": "The Waltz", "what": "A crop grows and is harvested.",
        "physics": "A growing canopy adds volume, so HV climbs pass after pass. Harvest removes it "
                   "and the dot glides back to bare soil, ready for the next season.",
        "carried_by": ["HV"], "future": "Crop calendars and yield early warnings for every farming "
        "region on Earth, cloud or no cloud.",
    },
    "shimmer": {
        "name": "The Shimmer", "what": "Rain wets the soil.",
        "physics": "Water raises the soil's dielectric constant, so the whole scene brightens a "
                   "little in both channels at once and fades within days. It is not a change on "
                   "the ground, and treating it as one would cause false alarms.",
        "carried_by": ["HH", "HV"], "future": "Soil moisture for drought and irrigation planning.",
    },
    "melt": {
        "name": "The Melt", "what": "Snow and ice melt at the surface.",
        "physics": "Liquid water in snow absorbs the radar, so melting ice turns dark. When it "
                   "refreezes, it brightens again. Over ice NISAR listens with HH alone.",
        "carried_by": ["HH"], "future": "Melt onset and duration across Greenland and Antarctica, "
        "every 12 days.",
    },
}

ZONES = [
    {"id": "water", "label": "Open water", "center": [-24, -32]},
    {"id": "soil", "label": "Bare soil", "center": [-13, -25]},
    {"id": "crops", "label": "Grass and crops", "center": [-10, -19]},
    {"id": "forest", "label": "Forest", "center": [-7, -13]},
    {"id": "bounce", "label": "Double bounce: flooded forest, cities, paddies", "center": [0, -12]},
]


def load_stage(raw: Path, sid: str):
    d = raw / sid
    if not (d / "cube.npz").exists() or not (d / "moves.npz").exists():
        return None
    z, m = np.load(d / "cube.npz"), np.load(d / "moves.npz")
    info = json.loads((d / "stage.json").read_text())
    return z, m, info


def canonical_path(raw: Path, stages: list[str], move: str, n_max: int = 4000):
    """Median HH/HV path of confident blocks doing `move`, aligned on their move's timing."""
    k = MOVE_IDS.index(move)
    paths = []
    used = []
    for sid in stages:
        got = load_stage(raw, sid)
        if got is None:
            continue
        z, m, _ = got
        hh = z["blocks_HH"].astype("float32")
        t_n = hh.shape[0]
        H = hh.reshape(t_n, -1)
        V = z["blocks_HV"].astype("float32").reshape(t_n, -1) if "blocks_HV" in z.files else None
        sel = np.flatnonzero((m["move"] == k) & (m["conf"] >= 60))
        if sel.size == 0:
            continue
        sel = sel[: n_max]
        used.append(sid)
        if move in ("fall", "scorch") and "split" in m.files:
            split = m["split"][sel].astype(int)
            rel = []
            for off in range(-2, 3):
                t = np.clip(split + off, 0, t_n - 1)
                h = np.nanmedian(H[t, sel])
                v = np.nanmedian(V[t, sel]) if V is not None else None
                rel.append((h, v))
            paths.append(rel)
        else:
            beats = m["beat_move"].reshape(t_n, -1)[:, sel] if "beat_move" in m.files else None
            # the whole season: median over the selected blocks at every pass
            rel = []
            for t in range(t_n):
                h = float(np.nanmedian(H[t, sel]))
                v = float(np.nanmedian(V[t, sel])) if V is not None else None
                rel.append((h, v))
            if move in ("vanish", "bounce", "melt") and beats is not None:
                # keep the passes around the move: from two before its first beat to two after its last
                on = (beats == k).mean(1) > 0.3
                if on.any():
                    i0, i1 = max(0, np.argmax(on) - 2), min(t_n, len(on) - np.argmax(on[::-1]) + 2)
                    rel = rel[i0:i1]
            paths.append(rel)
    if not paths:
        return None, used
    best = max(paths, key=len)
    return [{"HH": round(float(h), 2), "HV": (round(float(v), 2) if v is not None else None)}
            for h, v in best], used


def build_moves(raw: Path, stage_moves: dict[str, str], report: dict | None) -> dict:
    by_move: dict[str, list[str]] = {}
    for sid, mv in stage_moves.items():
        by_move.setdefault(mv, []).append(sid)
    extra = {"bounce": ["punjab", "edouard", "tonle_sap"], "waltz": ["iowa", "punjab"],
             "vanish": ["indiana", "okavango", "sylhet"]}
    moves = []
    for mv in MOVE_IDS:
        g = dict(GUIDE[mv])
        stages = list(dict.fromkeys(extra.get(mv, []) + by_move.get(mv, [])))
        path, used = (canonical_path(raw, stages, mv) if mv not in ("still", "shimmer")
                      else (None, []))
        if mv == "still":
            path = [{"HH": -7.2, "HV": -13.1}, {"HH": -7.0, "HV": -13.3}, {"HH": -7.3, "HV": -13.0}]
        metrics = None
        if report and mv in report["main"]:
            r = report["main"][mv]
            metrics = {k: r.get(k) for k in ("auprc", "auprc_ci", "f1", "f1_ci", "precision",
                                             "recall", "base_rate", "n")}
        moves.append({"id": mv, **g, "path": path, "path_from": used,
                      "path_note": None if mv != "still" else "illustrative: a stable forest hectare",
                      "metrics": metrics, "stages": by_move.get(mv, []) or stages})
    return {"fixture": False, "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "floor": {"x": {"pol": "HH", "min": -30, "max": 5},
                      "y": {"pol": "HV", "min": -38, "max": -5}, "zones": ZONES},
            "moves": moves}


def cross_continent(raw: Path) -> list[dict]:
    from_report = []
    for sid, move in (("rondonia", "fall"), ("apui", "fall"), ("morton", "fall")):
        d = raw / sid
        if not (d / "refs.npz").exists() or not (d / "moves.npz").exists():
            continue
        r, m = np.load(d / "refs.npz"), np.load(d / "moves.npz")
        if "dist_frac" not in r.files or "proba" not in m.files:
            continue
        frac = r["dist_frac"].ravel()
        p = m["proba"][:, 1]  # CLASSES = still, fall, scorch, vanish, waltz
        ok = np.isfinite(frac) & np.isfinite(p)
        y = (frac[ok] >= 0.5).astype(int)
        if y.sum() < 10:
            from_report.append({"stage": sid, "move": move, "reference": "OPERA DIST-ALERT-HLS",
                                "auprc": None, "base_rate": float(y.mean()) if ok.any() else None,
                                "n_blocks": int(ok.sum()), "note": "too few reference positives"})
            continue
        order = np.argsort(-p[ok])
        yy = y[order]
        prec = np.cumsum(yy) / np.arange(1, len(yy) + 1)
        ap = float((prec * yy).sum() / yy.sum())
        flag = m["move"].ravel()[ok] == 1
        tp = int((flag & (y == 1)).sum())
        from_report.append({
            "stage": sid, "move": move, "reference": "OPERA DIST-ALERT-HLS", "auprc": round(ap, 3),
            "base_rate": round(float(y.mean()), 4), "n_blocks": int(ok.sum()),
            "n_positive": int(y.sum()), "precision": round(tp / max(int(flag.sum()), 1), 3),
            "recall": round(tp / max(int(y.sum()), 1), 3)})
    return from_report


def build_proof(raw: Path, report: dict, scorecard: dict, run_stats: dict, n_stages: int,
                countries: int) -> dict:
    main = report["main"]
    names = {m: GUIDE[m]["name"] for m in GUIDE}
    refs_ = {"fall": "OPERA DIST-ALERT-HLS (optical forest loss)",
             "scorch": "NIFC fire perimeters", "vanish": "OPERA DSWx (optical/radar water maps)",
             "waltz": "USDA Cropland Data Layer (cultivated land)",
             "still": "Stable sites + blocks the references call unchanged"}
    moves = []
    for c in report["classes"]:
        r = main[c]
        moves.append({"id": c, "name": names[c], "reference": refs_[c],
                      "auprc": r["auprc"], "auprc_ci": r.get("auprc_ci"), "base_rate": r["base_rate"],
                      "precision": r["precision"], "recall": r["recall"], "f1": r["f1"],
                      "f1_ci": r.get("f1_ci"), "n_test_blocks": r["n"]})
    pol = {"classes": [c for c in report["classes"] if c != "still"], "variants": []}
    for name, r in report["ablations"].items():
        pol["variants"].append({
            "name": name,
            "auprc": {c: r[c]["auprc"] for c in pol["classes"]},
            "auprc_ci": {c: r[c].get("auprc_ci") for c in pol["classes"]}})
    s1 = None
    er = next((e for e in scorecard.get("equal_recall", []) if e["class"] == "forest_loss"), None)
    cl = {(c["class"], c["detector"]): c for c in scorecard.get("classes", [])
          if c.get("landcover") == "all"}
    if er and ("forest_loss", "L") in cl:
        L, C = cl[("forest_loss", "L")], cl[("forest_loss", "C")]
        s1 = {"n_sites": L["n_sites"], "recall": er["recall"],
              "precision_nisar": round(er["precision_L"], 3), "precision_s1": round(er["precision_C"], 3),
              "ratio": round(er["ratio_L_over_C"], 1),
              "auprc_nisar": round(L["auprc"], 3), "auprc_nisar_ci": [round(L["ci_low"], 3), round(L["ci_high"], 3)],
              "auprc_s1": round(C["auprc"], 3), "auprc_s1_ci": [round(C["ci_low"], 3), round(C["ci_high"], 3)]}
    return {
        "fixture": False, "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "headline": {
            "reference_sites": int(main["n_train_sites"] + main["n_test_sites"]),
            "train_sites": main["n_train_sites"], "test_sites": main["n_test_sites"],
            "test_states": main["n_test_states"],
            "hectares_scored": int(main["n_train_blocks"] + main["n_test_blocks"]),
            "passes_read": run_stats.get("passes_read"), "stages": n_stages, "countries": countries},
        "moves": moves,
        "macro_f1": {"value": main["macro_f1_moves"], "ci": main.get("macro_f1_moves_ci")},
        "confusion": main["confusion"],
        "polarization": pol,
        "importance_gain": report.get("importance_gain"),
        "sentinel1": s1,
        "cross_continent": cross_continent(raw),
        "limits": [
            "References are independent of NISAR but imperfect: optical forest-loss alerts miss "
            "cloudy weeks, fire perimeters include unburned patches, and the cropland map labels "
            "cultivated land rather than a dated harvest.",
            "The Bounce and the Melt have no labeled reference set here; they are physics rules, "
            "shown as such, not measured accuracies.",
            "Reference sites were chosen where each kind of change happened, so accuracy describes "
            "these sites, not how common each change is across the country.",
            "Held-out results come from states never used for training or tuning. Intervals "
            "resample whole sites, so they reflect how results vary from place to place.",
            "NISAR data are provisional releases (2025 to 2026); NASA reprocessing can shift values.",
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--web", type=Path, required=True)
    ap.add_argument("--scorecard", type=Path, required=True)
    args = ap.parse_args()
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from modal_app.stage_defs import STAGES

    stage_moves = {sid: s["move"] for sid, s in STAGES.items() if (args.raw / sid / "moves.npz").exists()}
    rp = args.raw / "_ref" / "moves_report.json"
    report = json.loads(rp.read_text()) if rp.exists() else None
    moves = build_moves(args.raw, stage_moves, report)
    (args.web / "moves.json").write_text(json.dumps(moves, indent=1))
    print("moves.json:", [(m["id"], len(m["path"] or [])) for m in moves["moves"]])
    if report:
        sc = json.loads(args.scorecard.read_text()) if args.scorecard.exists() else {}
        rs = args.raw / "_ref" / "run_stats.json"
        run_stats = json.loads(rs.read_text()) if rs.exists() else {}
        countries = len({STAGES[s]["country"] for s in stage_moves})
        proof = build_proof(args.raw, report, sc, run_stats, len(stage_moves), countries)
        (args.web / "proof.json").write_text(json.dumps(proof, indent=1, default=float))
        print("proof.json written; cross-continent:", proof["cross_continent"])


if __name__ == "__main__":
    main()

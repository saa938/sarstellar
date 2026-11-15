"""Batch job: read every NISAR pass over each SARstellar v2 stage, on Modal.

    modal run modal_app/dance.py                      (all stages)
    modal run modal_app/dance.py --only punjab,iowa
    modal run modal_app/dance.py --only punjab --render-only

One container per granule reads its window (`read_granule`); `stage_job` composites dates and
writes to the Volume `sarstellar-data` under `dance/<id>/`:
  cube.npz      blocks_<pol> [T, ny, nx] float16 dB, valid_frac [T, ny, nx] uint8 (%), dates
  image.npz     img_<pol> [T, nyi, nxi] uint8 quantized dB (0 = no data), for re-rendering
  img/NNN.webp  radar false color per date (R = HH, G = HV, B = HH/HV), alpha = no data
  stage.json    grid, corners, stack, dates, per-granule read metadata, errors
"""


import io
import json
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1]
DATA = "/data"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .add_local_file(ROOT / "pyproject.toml", "/repo/pyproject.toml", copy=True)
    .add_local_dir(ROOT / "core", "/repo/core", copy=True,
                   ignore=["**/__pycache__", "**/*.pyc", "**/*.egg-info"])
    .run_commands("pip install '/repo[ml]' umap-learn fastapi")
    .add_local_python_source("modal_app")
)

app = modal.App("sarstellar-dance", image=image)
volume = modal.Volume.from_name("sarstellar-data", create_if_missing=True)
earthdata = modal.Secret.from_name("earthdata")
live_jobs = modal.Dict.from_name("sarstellar-live-jobs", create_if_missing=True)
import os as _os  # noqa: E402

import threading as _threading  # noqa: E402

_COMMIT_LOCK = _threading.Lock()


def _commit() -> None:
    """Volume commits from concurrent inputs in one container, one at a time."""
    with _COMMIT_LOCK:
        volume.commit()


LIVE_KILL = _os.environ.get("SARSTELLAR_KILL", "") if modal.is_local() else ""
LIVE_MAX_KM = 25.0
LIVE_PER_IP_HOUR = 8
LIVE_PER_DAY = 200


@app.function(secrets=[earthdata], timeout=900, retries=2, cpu=2.0, memory=8192,
              max_containers=400)
def read_granule(url: str, grid_dict: dict, img_res: float):
    import numpy as np

    from sarstellar.dance import read_stage_granule
    from sarstellar.types import Grid

    res = read_stage_granule(url, Grid(**grid_dict), img_res)
    if res is None:
        return None
    meta, blocks, img = res
    buf = io.BytesIO()
    np.savez(buf, **{f"b_{k}": v for k, v in blocks.items()},
             **{f"i_{k}": v for k, v in img.items()})
    return meta, buf.getvalue()


def _render(images: dict, out_dir: Path, hh_only: bool) -> dict:
    """False-color WebP per date with one stretch for the whole stage."""
    import numpy as np
    from PIL import Image

    from sarstellar.dance import IMG_DB_MAX, IMG_DB_MIN

    def to_db(b):
        return np.where(b > 0, IMG_DB_MIN + (b.astype("float32") - 1) / 254 *
                        (IMG_DB_MAX - IMG_DB_MIN), np.nan)

    hh = to_db(images["HH"])
    t, ny, nx = hh.shape
    stretch = {}

    def stretch_of(name, a, lo_q=2, hi_q=98):
        v = a[np.isfinite(a)]
        lo, hi = (float(np.percentile(v, lo_q)), float(np.percentile(v, hi_q))) if v.size else (-30, 0)
        stretch[name] = [round(lo, 2), round(hi, 2)]
        return lo, hi

    def scale(a, lo, hi):
        return np.clip((a - lo) / max(hi - lo, 1e-6), 0, 1)

    (out_dir / "img").mkdir(parents=True, exist_ok=True)
    files = []
    if hh_only:
        lo, hi = -20.0, -2.0
        stretch.update({"HH": [lo, hi], "scheme": "HH ice ramp"})
        for i in range(t):
            s = scale(hh[i], lo, hi)
            alpha = np.isfinite(hh[i])
            # ice ramp: deep blue (dark) to white (bright)
            r = np.nan_to_num(40 + 215 * s ** 1.4)
            g = np.nan_to_num(70 + 185 * s ** 1.1)
            b = np.nan_to_num(110 + 145 * s ** 0.8)
            rgba = np.dstack([r, g, b, alpha * 255]).astype("uint8")
            name = f"img/{i:03d}.webp"
            Image.fromarray(rgba, "RGBA").save(out_dir / name, "WEBP", quality=82, method=4)
            files.append(name)
    else:
        # R = HH, G = HV, B = HH on fixed dB ranges (comparable across stages): open water black,
        # vegetation green, bare soil dim violet, double bounce (cities, flooded trees, rice) pink
        # to white.
        hv = to_db(images["HV"])
        lo_h, hi_h = -22.0, 2.0
        lo_v, hi_v = -30.0, -8.0
        stretch.update({"HH": [lo_h, hi_h], "HV": [lo_v, hi_v],
                        "scheme": "R=HH^1.5 G=HV^0.9 B=HH^1.7"})
        for i in range(t):
            alpha = np.isfinite(hh[i]) & np.isfinite(hv[i])
            r = np.nan_to_num(scale(hh[i], lo_h, hi_h) ** 1.5 * 255)
            g = np.nan_to_num(scale(hv[i], lo_v, hi_v) ** 0.9 * 255)
            b = np.nan_to_num(scale(hh[i], lo_h, hi_h) ** 1.7 * 230)
            rgba = np.dstack([r, g, b, alpha * 255]).astype("uint8")
            name = f"img/{i:03d}.webp"
            Image.fromarray(rgba, "RGBA").save(out_dir / name, "WEBP", quality=84, method=4)
            files.append(name)
    # thumbnail from the date with the most valid pixels in the second half of the series
    valid_counts = [(int(np.isfinite(hh[i]).sum()), i) for i in range(t // 2, t)]
    best = max(valid_counts)[1] if valid_counts else 0
    th = Image.open(out_dir / files[best])
    th.thumbnail((640, 640))
    th.save(out_dir / "img/thumb.webp", "WEBP", quality=80)
    return {"files": files, "stretch": stretch, "nx": nx, "ny": ny, "thumb_index": best}


def run_stage(stage_id: str, spec: dict, out: Path, progress=None) -> dict:
    """The whole stage pipeline: search, parallel reads, composite, cube + images + stage.json.

    `progress(fraction, message)` is called as passes arrive (the live API shows it).
    """
    import time
    from collections import defaultdict
    from dataclasses import asdict
    from datetime import date

    import numpy as np

    from modal_app.stage_defs import END, START
    from sarstellar.dance import composite, probe_epsg, stage_stacks
    from sarstellar.grid import grid_for_bbox, lonlat_corners

    def tick(frac, msg):
        if progress:
            progress(frac, msg)

    t0 = time.time()
    bbox = spec["bbox"]
    start = date.fromisoformat(spec.get("start", START))
    end = date.fromisoformat(spec.get("end", END))
    tick(0.02, "Searching NASA's archive for NISAR passes")
    stacks = stage_stacks(bbox, start, end)
    if spec.get("mode"):
        stacks = [s for s in stacks if s.mode == spec["mode"]]
    if spec.get("track"):
        stacks = [s for s in stacks if s.track == spec["track"]]
    if not stacks:
        return {"id": stage_id, "error": "NISAR has no calibrated passes over this box yet."}
    st = stacks[0]
    epsg = probe_epsg(st.granules[0].url)
    grid = grid_for_bbox(bbox, epsg)
    gd = asdict(grid)
    by_date = st.granules_by_date()
    calls = [(d, g) for d, gs in by_date.items() for g in gs]
    tick(0.08, f"Reading {len(calls)} NISAR passes in parallel")
    per_date: dict = defaultdict(list)
    errors = []
    done = 0
    args = [(g.url, gd, float(spec.get("img_res", 20.0))) for _, g in calls]
    by_url = {g.url: (d, g) for d, g in calls}
    for (url, r) in zip([a[0] for a in args], read_granule.starmap(args, return_exceptions=True)):
        done += 1
        d, g = by_url[url]
        tick(0.08 + 0.72 * done / len(calls), f"Read pass {done} of {len(calls)} ({d})")
        if isinstance(r, BaseException):
            errors.append({"granule": g.ur, "error": f"{type(r).__name__}: {str(r)[:200]}"})
            continue
        if r is None:
            errors.append({"granule": g.ur, "error": "skipped: other UTM zone, posting, or no overlap"})
            continue
        meta, payload = r
        z = np.load(io.BytesIO(payload))
        blocks = {k[2:]: z[k] for k in z.files if k.startswith("b_")}
        img = {k[2:]: z[k] for k in z.files if k.startswith("i_")}
        per_date[d].append((meta, blocks, img))

    dates, comps = [], []
    ny, nx = grid.shape
    for d in sorted(per_date):
        c = composite(per_date[d], grid)
        frac_valid = float(np.isfinite(c["blocks"]["HH"]).mean())
        if frac_valid < 0.2:
            errors.append({"date": str(d), "error": f"only {frac_valid:.0%} of blocks valid; dropped"})
            continue
        dates.append(d)
        comps.append(c)
    if len(dates) < 2:
        return {"id": stage_id, "error": "Fewer than two usable NISAR passes over this box.",
                "errors": errors[:20], "stacks": [s.summary() for s in stacks[:5]]}

    tick(0.82, "Composing the dance")
    pols = [p for p in ("HH", "HV", "VV") if all(p in c["blocks"] for c in comps)]
    cube = {f"blocks_{p}": np.stack([c["blocks"][p] for c in comps]).astype("float16") for p in pols}
    cube["valid_frac"] = np.stack([np.round(c["blocks"]["valid_frac"] * 100)
                                   for c in comps]).astype("uint8")
    cube["dates"] = np.array([str(d) for d in dates])
    img_shape = max({c["image"]["HH"].shape for c in comps})
    images = {}
    for p in pols:
        arr = np.zeros((len(comps), *img_shape), dtype="uint8")
        for i, c in enumerate(comps):
            a = c["image"][p]
            arr[i, : a.shape[0], : a.shape[1]] = a
        images[f"img_{p}"] = arr
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / "cube.npz", **cube)
    np.savez_compressed(out / "image.npz", **images)
    info = {
        "id": stage_id, "spec": spec, "grid": gd, "shape": [ny, nx],
        "corners": lonlat_corners(grid), "stack": st.summary(),
        "other_stacks": [s.summary() for s in stacks[1:6]],
        "dates": [str(d) for d in dates], "pols": pols,
        "metas": [m for c in comps for m in c["metas"]],
        "errors": errors, "img_shape": list(img_shape),
        "img_res_m": comps[0]["metas"][0]["img_res_m"],
    }
    tick(0.88, "Rendering radar images")
    info["render"] = _render({p: images[f"img_{p}"] for p in pols}, out, hh_only="HV" not in pols)
    info["elapsed_s"] = round(time.time() - t0, 1)
    (out / "stage.json").write_text(json.dumps(info, indent=1))
    return {"id": stage_id, "n_dates": len(dates), "pols": pols, "shape": [ny, nx],
            "img": list(img_shape), "stack": st.summary(), "n_errors": len(errors),
            "elapsed_s": info["elapsed_s"], "n_reads": len(calls)}


@app.function(secrets=[earthdata], volumes={DATA: volume}, timeout=3600, cpu=4.0,
              memory=32768, max_containers=10)
def stage_job(stage_id: str, spec: dict, render_only: bool = False) -> dict:
    import numpy as np

    out = Path(DATA) / "dance" / stage_id
    if render_only:
        info = json.loads((out / "stage.json").read_text())
        z = np.load(out / "image.npz")
        images = {k[4:]: z[k] for k in z.files if k.startswith("img_")}
        info["render"] = _render(images, out, hh_only="HV" not in images)
        (out / "stage.json").write_text(json.dumps(info, indent=1))
        _commit()
        return {"id": stage_id, "rendered": len(info["render"]["files"])}
    if (out / "stage.json").exists() and not spec.get("force"):
        return {"id": stage_id, "cached": True}
    res = run_stage(stage_id, spec, out)
    _commit()
    return res


@app.function(secrets=[earthdata], volumes={DATA: volume}, timeout=1800, cpu=1.0,
              memory=8192, max_containers=24)
def ref_site_job(site: dict) -> dict:
    """Full series for one scorecard reference site, on exactly the scorecard's block grid."""
    from collections import defaultdict
    from dataclasses import asdict
    from datetime import date, timedelta

    import numpy as np

    from sarstellar.dance import composite, probe_epsg, stage_stacks
    from sarstellar.grid import grid_for_bbox

    sid, meta, bbox = site["id"], site["meta"], site["bbox"]
    out = Path(DATA) / "dance_ref" / f"{sid}.npz"
    if out.exists():
        return {"id": sid, "cached": True}
    try:
        d0, d1 = (date.fromisoformat(x) for x in meta["pair_dates"])
        stacks = [s for s in stage_stacks(bbox, d0 - timedelta(days=60), d1 + timedelta(days=45))
                  if s.track == meta["track"] and s.direction == meta["direction"]
                  and s.crid == meta["crid"]]
        if not stacks:
            return {"id": sid, "error": "no matching stack"}
        pair = set(site["nisar_pair"])
        stacks.sort(key=lambda s: (-len(pair & {g.ur for g in s.granules}), -len(s.dates)))
        st = stacks[0]
        g0 = next((g for g in st.granules if g.ur in pair), st.granules[0])
        grid = grid_for_bbox(bbox, probe_epsg(g0.url))
        gd = asdict(grid)
        calls = [(d, g) for d, gs in st.granules_by_date().items() for g in gs]
        results = list(read_granule.starmap([(g.url, gd, 100.0) for _, g in calls],
                                            return_exceptions=True))
        per_date: dict = defaultdict(list)
        n_err = 0
        for (d, _), r in zip(calls, results):
            if isinstance(r, BaseException) or r is None:
                n_err += isinstance(r, BaseException)
                continue
            m, payload = r
            z = np.load(io.BytesIO(payload))
            per_date[d].append((m, {k[2:]: z[k] for k in z.files if k.startswith("b_")}, {}))
        dates, comps = [], []
        for d in sorted(per_date):
            c = composite(per_date[d], grid)
            if np.isfinite(c["blocks"]["HH"]).mean() >= 0.2:
                dates.append(d)
                comps.append(c)
        if len(dates) < 3:
            return {"id": sid, "error": f"only {len(dates)} usable dates", "n_err": n_err}
        pols = [p for p in ("HH", "HV", "VV") if all(p in c["blocks"] for c in comps)]
        out.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            out, dates=np.array([str(d) for d in dates]),
            pair_dates=np.array(meta["pair_dates"]),
            **{f"blocks_{p}": np.stack([c["blocks"][p] for c in comps]).astype("float16")
               for p in pols})
        _commit()
        return {"id": sid, "n_dates": len(dates), "shape": list(grid.shape), "pols": pols,
                "n_err": n_err}
    except Exception as exc:  # noqa: BLE001 - one bad site never stops the batch
        return {"id": sid, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}


@app.function(volumes={DATA: volume}, timeout=3600, cpu=8.0, memory=65536)
def build_ref_table(max_still_per_site: int = 20000) -> dict:
    """Join every reference site's series features with its scorecard labels -> train.parquet."""
    import numpy as np
    import pandas as pd

    from sarstellar.moves import FEATURES, LABEL_TO_MOVE, block_features

    volume.reload()
    bt = pd.read_parquet(Path(DATA) / "scorecard" / "blocks.parquet",
                         columns=["site", "state", "kind", "split", "label", "valid"])
    rng = np.random.default_rng(20261115)
    parts, notes = [], []
    for sid, g in bt.groupby("site", sort=False):
        path = Path(DATA) / "dance_ref" / f"{sid}.npz"
        if not path.exists():
            notes.append({"id": sid, "note": "no series"})
            continue
        z = np.load(path)
        if "blocks_HV" not in z.files:
            notes.append({"id": sid, "note": "no HV"})
            continue
        hh, hv = z["blocks_HH"].astype("float32"), z["blocks_HV"].astype("float32")
        t_n, ny, nx = hh.shape
        if ny * nx != len(g):
            notes.append({"id": sid, "note": f"grid {ny}x{nx} != {len(g)} labels"})
            continue
        f = block_features(hh, hv, (ny, nx))
        df = pd.DataFrame({k: f[k] for k in FEATURES})
        df["block"] = np.arange(ny * nx)
        df["step_t"] = f["split"]
        for col in ("site", "state", "kind", "split", "label"):
            df[col] = g[col].to_numpy()
        df["valid"] = f["valid"] & g["valid"].to_numpy()
        df = df[df["valid"] & df["label"].isin(list(LABEL_TO_MOVE))]
        df["move"] = df["label"].map(LABEL_TO_MOVE)
        still = df[df["move"] == "still"]
        if len(still) > max_still_per_site:
            keep = rng.choice(len(still), max_still_per_site, replace=False)
            df = pd.concat([df[df["move"] != "still"], still.iloc[keep]])
        df["n_series"] = t_n
        parts.append(df)
    table = pd.concat(parts, ignore_index=True)
    table.to_parquet(Path(DATA) / "dance_ref" / "train.parquet")
    _commit()
    counts = table.groupby(["split", "move"]).size().unstack(fill_value=0).to_dict()
    return {"rows": len(table), "sites": int(table["site"].nunique()), "counts": counts,
            "notes": notes[:40], "n_notes": len(notes)}


@app.function(volumes={DATA: volume}, timeout=3600, cpu=16.0, memory=65536)
def train_moves(n_boot: int = 300, source: str = "pairs") -> dict:
    """Fit the move model on training states; measure it (and the HH/HV ablations) on held-out states.

    source="pairs": the scorecard's two-pass table (2.2M reference hectares, no new reads).
    source="series": dance_ref/train.parquet built from full series (needs the refs job).
    """
    import pickle

    import pandas as pd

    from sarstellar.moves_model import PAIR_ABLATIONS, pair_table, run_all

    volume.reload()
    d = Path(DATA) / "dance_ref"
    d.mkdir(parents=True, exist_ok=True)
    if source == "pairs":
        blocks = pd.read_parquet(Path(DATA) / "scorecard" / "blocks.parquet",
                                 columns=["site", "state", "kind", "split", "label", "valid",
                                          "rel_HH", "rel_HV"])
        table = pair_table(blocks)
        model, report = run_all(table, n_boot=n_boot, ablations=PAIR_ABLATIONS)
    else:
        table = pd.read_parquet(d / "train.parquet")
        model, report = run_all(table, n_boot=n_boot)
    report["source"] = source
    (d / "moves_model.pkl").write_bytes(pickle.dumps(model))
    (d / "moves_model_meta.json").write_text(json.dumps({"features": report["features"],
                                                          "source": source}))
    (d / "moves_report.json").write_text(json.dumps(report, indent=1, default=float))
    _commit()
    main = report["main"]
    out = {c: {k: main[c][k] for k in ("precision", "recall", "f1", "auprc", "n")}
           for c in report["classes"]} | {"macro_f1_moves": main["macro_f1_moves"],
                                          "gated": main.get("gated")}
    return json.loads(json.dumps(out, default=float))  # plain floats: the local client has no numpy


@app.function(volumes={DATA: volume}, timeout=1800, cpu=4.0, memory=32768, max_containers=20)
def apply_stage(stage_id: str, headline: str) -> dict:
    """Moves for one stage: per block (move, confidence, class probabilities) and per beat."""
    import pickle

    import numpy as np

    from sarstellar.moves import MOVE_IDS
    from sarstellar.moves_model import CLASSES, apply_to_stage, pick_highlights

    volume.reload()
    src = Path(DATA) / "dance" / stage_id
    if not (src / "cube.npz").exists():
        return {"id": stage_id, "error": "no cube"}
    model = pickle.loads((Path(DATA) / "dance_ref" / "moves_model.pkl").read_bytes())
    feats = json.loads((Path(DATA) / "dance_ref" / "moves_model_meta.json").read_text())["features"]
    z = np.load(src / "cube.npz")
    cube = {k: z[k] for k in z.files if k.startswith("blocks_")}
    res = apply_to_stage(model, cube, feats)
    counts = {m: int((res["move"] == i).sum()) for i, m in enumerate(MOVE_IDS)}
    extra = {}
    f = res.get("features")
    if f is not None:
        X = np.stack([f[k] for k in feats], axis=1)
        proba = np.full((X.shape[0], len(CLASSES)), np.nan, dtype="float32")
        ok = f["valid"]
        proba[ok] = model.predict_proba(X[ok].astype("float32"))
        extra["proba"] = proba
        extra["split"] = f["split"]
    np.savez_compressed(src / "moves.npz", move=res["move"], conf=res["conf"],
                        beat_move=res["beat_move"], counts=json.dumps(counts), **extra)
    hl = pick_highlights(res, cube, headline)
    (src / "highlight.json").write_text(json.dumps({"blocks": hl, "label": headline}))
    _commit()
    return json.loads(json.dumps({"id": stage_id, "counts": counts, "highlights": len(hl)}, default=float))


@app.function(secrets=[earthdata], volumes={DATA: volume}, timeout=1800, cpu=4.0,
              memory=16384, max_containers=10)
def stage_refs(stage_id: str, kind: str) -> dict:
    """Independent optical references on a stage grid (for the cross-continent test)."""
    from datetime import date

    import numpy as np

    from sarstellar import read, refs_scoring
    from sarstellar.types import Grid

    volume.reload()
    src = Path(DATA) / "dance" / stage_id
    info = json.loads((src / "stage.json").read_text())
    grid = Grid(**info["grid"])
    dates = [date.fromisoformat(d) for d in info["dates"]]
    fs = read.https_fs()
    out = {}
    try:
        if kind == "fall":
            out["dist_frac"] = np.asarray(
                refs_scoring.dist_hls_loss(grid, dates[0], dates[-1], fs=fs), dtype="float32")
        elif kind == "vanish":
            water = []
            for d in dates:
                try:
                    water.append(np.asarray(refs_scoring.dswx_water(grid, d, fs=fs, max_days=4),
                                            dtype="float32"))
                except Exception:  # noqa: BLE001 - a date without DSWx stays NaN
                    water.append(np.full(grid.shape, np.nan, dtype="float32"))
            out["water"] = np.stack(water)
    except Exception as exc:  # noqa: BLE001
        return {"id": stage_id, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    np.savez_compressed(src / "refs.npz", **out)
    _commit()
    return {"id": stage_id, "kind": kind,
            "known": {k: float(np.isfinite(v).mean()) for k, v in out.items()}}


@app.function(volumes={DATA: volume}, timeout=3600, cpu=16.0, memory=65536)
def constellation(per_stage: int = 25000, seed: int = 7) -> dict:
    """Every stage's hectares placed by the shape of their dance (UMAP of the move features)."""
    import numpy as np
    import umap

    from modal_app.stage_defs import STAGES
    from sarstellar.moves import FEATURES, block_features

    volume.reload()
    rng = np.random.default_rng(seed)
    rows, meta = [], []
    stage_ids = []
    for sid in STAGES:
        src = Path(DATA) / "dance" / sid
        if not (src / "cube.npz").exists() or not (src / "moves.npz").exists():
            continue
        z = np.load(src / "cube.npz")
        if "blocks_HV" not in z.files:
            continue
        hh, hv = z["blocks_HH"].astype("float32"), z["blocks_HV"].astype("float32")
        f = block_features(hh, hv, hh.shape[1:])
        mv = np.load(src / "moves.npz")["move"]
        ok = np.flatnonzero(f["valid"] & (mv != 255))
        # keep every moving block (up to half the budget) plus a random sample of still ones
        moving = ok[mv[ok] != 0]
        still = ok[mv[ok] == 0]
        take_m = rng.choice(moving, min(len(moving), per_stage // 2), replace=False) if len(moving) else moving
        take_s = rng.choice(still, min(len(still), per_stage - len(take_m)), replace=False) if len(still) else still
        take = np.concatenate([take_m, take_s])
        X = np.stack([f[k][take] for k in FEATURES], axis=1)
        good = np.isfinite(X).all(1)
        rows.append(X[good])
        meta.append(np.stack([np.full(good.sum(), len(stage_ids)), take[good], mv[take[good]]], 1))
        stage_ids.append(sid)
    X = np.concatenate(rows).astype("float32")
    M = np.concatenate(meta)
    mu, sd = X.mean(0), X.std(0) + 1e-6
    emb = umap.UMAP(n_neighbors=30, min_dist=0.08, random_state=seed, low_memory=True).fit_transform((X - mu) / sd)
    emb = (emb - emb.min(0)) / (emb.max(0) - emb.min(0))
    out = Path(DATA) / "dance" / "_constellation.npz"
    np.savez_compressed(out, xy=emb.astype("float32"), stage=M[:, 0].astype("uint8"),
                        block=M[:, 1].astype("uint32"), move=M[:, 2].astype("uint8"),
                        stage_ids=np.array(stage_ids))
    _commit()
    return {"points": int(len(X)), "stages": stage_ids}


def _set_job(job_id: str, **fields) -> None:
    cur = live_jobs.get(job_id) or {}
    cur.update(fields)
    live_jobs[job_id] = cur


@app.function(secrets=[earthdata], volumes={DATA: volume}, timeout=1800, cpu=4.0,
              memory=32768, max_containers=4)
def live_job(job_id: str, bbox: list[float]) -> None:
    """A user's box, anywhere: the full stage pipeline + moves, written as a web bundle."""
    import pickle
    import time

    import numpy as np

    from sarstellar.bundle import write_bundle
    from sarstellar.moves import MOVE_IDS
    from sarstellar.moves_model import apply_to_stage, pick_highlights

    t0 = time.time()
    root = Path(DATA) / "live" / job_id
    _set_job(job_id, status="running", progress=0.01, message="Starting")

    def progress(frac, msg):
        _set_job(job_id, progress=round(frac, 3), message=msg)

    try:
        spec = {"bbox": bbox, "name": "Your stage", "country": ""}
        res = run_stage(job_id, spec, root / "raw", progress)
        if "error" in res:
            _set_job(job_id, status="error", message=res["error"])
            return
        progress(0.92, "Recognizing the moves")
        volume.reload()
        model = pickle.loads((Path(DATA) / "dance_ref" / "moves_model.pkl").read_bytes())
        feats = json.loads((Path(DATA) / "dance_ref" / "moves_model_meta.json").read_text())["features"]
        z = np.load(root / "raw" / "cube.npz")
        cube = {k: z[k] for k in z.files if k.startswith("blocks_")}
        mv = apply_to_stage(model, cube, feats)
        counts = {m: int((mv["move"] == i).sum()) for i, m in enumerate(MOVE_IDS)}
        np.savez_compressed(root / "raw" / "moves.npz", move=mv["move"], conf=mv["conf"],
                            beat_move=mv["beat_move"], counts=json.dumps(counts))
        moving = {k: v for k, v in counts.items() if k != "still" and v}
        headline = max(moving, key=moving.get) if moving else "still"
        hl = pick_highlights(mv, cube, headline) if headline != "still" else []
        (root / "raw" / "highlight.json").write_text(json.dumps({"blocks": hl, "label": headline}))
        n = res["n_dates"]
        story = {
            "title": "Your stage", "move": headline,
            "lede": f"{n} NISAR passes over this box, read live from NASA's archive.",
            "body": [f"The most common move here is {headline}. Moves come from a model trained on "
                     "US reference sites; treat them as hypotheses to check on the ground."],
        }
        write_bundle(root / "raw", root / "bundle", story, sid=job_id)
        _commit()
        _set_job(job_id, status="done", progress=1.0, message="Done",
                 base=f"/dance/{job_id}/files/", n_dates=n, counts=counts,
                 elapsed_s=round(time.time() - t0, 1))
    except Exception as exc:  # noqa: BLE001 - the user sees a readable error, never a stack
        _set_job(job_id, status="error",
                 message=f"Something went wrong reading NASA's archive ({type(exc).__name__}). "
                         "Try again in a few minutes.")
        raise


@app.function(volumes={DATA: volume}, timeout=300, cpu=1.0, memory=2048,
              scaledown_window=1200)
@modal.concurrent(max_inputs=64)
@modal.asgi_app()
def live():
    import math
    import time
    import uuid

    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse

    api = FastAPI(title="SARstellar live")
    api.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"],
                       allow_headers=["*"])

    @api.get("/health")
    def health():
        return {"ok": True, "paused": bool(LIVE_KILL)}

    @api.post("/dance")
    async def create(req: Request):
        if LIVE_KILL:
            raise HTTPException(503, "Live analysis is paused; the saved stages still work.")
        body = await req.json()
        try:
            w, s_, e, n = (float(v) for v in body["bbox"])
        except Exception:
            raise HTTPException(422, "bbox must be [west, south, east, north] in degrees") from None
        if not (-180 <= w < e <= 180 and -85 <= s_ < n <= 85):
            raise HTTPException(422, "bbox must have west < east and south < north")
        km_x = (e - w) * 111.32 * math.cos(math.radians((s_ + n) / 2))
        km_y = (n - s_) * 110.57
        if max(km_x, km_y) > LIVE_MAX_KM or min(km_x, km_y) < 1.0:
            raise HTTPException(422, f"Draw a box between 1 and {LIVE_MAX_KM:.0f} km on a side.")
        key = "cache:" + ",".join(f"{v:.3f}" for v in (w, s_, e, n))
        hit = live_jobs.get(key)
        if hit and (live_jobs.get(hit) or {}).get("status") in ("queued", "running", "done"):
            return {"id": hit, "cached": True}
        ip = (req.headers.get("x-forwarded-for") or (req.client.host if req.client else "?")).split(",")[0]
        hour, day = int(time.time() // 3600), int(time.time() // 86400)
        k_ip, k_day = f"rate:{ip}:{hour}", f"rate:day:{day}"
        if (live_jobs.get(k_ip) or 0) >= LIVE_PER_IP_HOUR:
            raise HTTPException(429, "That's a lot of dancing for one hour. Try again later.")
        if (live_jobs.get(k_day) or 0) >= LIVE_PER_DAY:
            raise HTTPException(429, "Today's live analyses are used up; the saved stages still work.")
        live_jobs[k_ip] = (live_jobs.get(k_ip) or 0) + 1
        live_jobs[k_day] = (live_jobs.get(k_day) or 0) + 1
        job_id = uuid.uuid4().hex[:12]
        live_jobs[job_id] = {"status": "queued", "progress": 0.0, "message": "Queued",
                             "bbox": [w, s_, e, n], "created": time.time()}
        live_jobs[key] = job_id
        live_job.spawn(job_id, [w, s_, e, n])
        return {"id": job_id, "cached": False}

    @api.get("/dance/{job_id}")
    def status(job_id: str):
        job = live_jobs.get(job_id)
        if not job or not isinstance(job, dict):
            raise HTTPException(404, "No such analysis")
        return {"id": job_id, **job}

    @api.get("/dance/{job_id}/files/{path:path}")
    def files(job_id: str, path: str):
        root = (Path(DATA) / "live" / job_id / "bundle").resolve()
        target = (root / path).resolve()
        if root not in target.parents and target != root:
            raise HTTPException(404, "Not found")
        if not target.exists():
            volume.reload()
        if not target.exists():
            raise HTTPException(404, "Not found")
        media = {".json": "application/json", ".webp": "image/webp",
                 ".bin": "application/octet-stream"}.get(target.suffix, "application/octet-stream")
        return FileResponse(target, media_type=media,
                            headers={"Cache-Control": "public, max-age=86400"})

    return api


@app.local_entrypoint()
def stars():
    print(json.dumps(constellation.remote()))


@app.local_entrypoint()
def moves(train: bool = True, apply: bool = True, refs_only: bool = False, only: str = "",
          source: str = "pairs"):
    from modal_app.stage_defs import STAGES

    ids = [s for s in only.split(",") if s] or list(STAGES)
    if refs_only:
        jobs = [(i, STAGES[i]["move"]) for i in ids if STAGES[i]["move"] in ("fall", "vanish")]
        for r in stage_refs.starmap(jobs, return_exceptions=True):
            print(json.dumps(r if isinstance(r, dict) else {"error": repr(r)[:300]}))
        return
    if train:
        print(json.dumps(train_moves.remote(source=source), default=float, indent=1))
    if apply:
        for r in apply_stage.starmap([(i, STAGES[i]["move"]) for i in ids], return_exceptions=True):
            print(json.dumps(r if isinstance(r, dict) else {"error": repr(r)[:300]}))


@app.local_entrypoint()
def refs(limit: int = 0, table_only: bool = False):
    """Series for every scorecard site (fan-out), then the joined training table."""
    sites = json.loads((ROOT / "modal_app" / "data" / "sites.json").read_text())
    sites = [s for s in sites if s.get("nisar_pair") and s.get("meta")]
    if limit:
        sites = sites[:limit]
    if not table_only:
        ok = 0
        for r in ref_site_job.map(sites, return_exceptions=True):
            r = r if isinstance(r, dict) else {"error": repr(r)[:200]}
            ok += "error" not in r
            print(json.dumps(r))
        print(json.dumps({"sites_ok": ok, "sites": len(sites)}))
    print(json.dumps(build_ref_table.remote(), default=str)[:4000])


@app.local_entrypoint()
def main(only: str = "", render_only: bool = False):
    from modal_app.stage_defs import STAGES

    ids = [s for s in only.split(",") if s] or list(STAGES)
    args = [(i, STAGES[i], render_only) for i in ids]
    for r in stage_job.starmap(args, return_exceptions=True):
        print(json.dumps(r if isinstance(r, dict) else {"error": repr(r)[:300]}))

"""Turn a stage's Modal output (dance/<id>/ on the Volume, downloaded) into the web bundle.

    python science/export_stage.py --raw <dir with dance/<id>/ folders> --web web/public

Writes web/public/stages/<id>/{stage.json, blocks.bin, img/*.webp} per docs/v2/CONTRACT.md and
rebuilds web/public/stages/index.json from every stage present. Story text comes from
science/stories.py; moves (when computed) from <raw>/<id>/moves.npz.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stories import STORIES  # noqa: E402

SCALE, OFFSET, NODATA = 0.2, -40.0, 255
MOVE_IDS = ["still", "fall", "scorch", "bounce", "vanish", "waltz", "shimmer", "melt"]


def quantize(db: np.ndarray) -> np.ndarray:
    q = np.round((db.astype("float32") - OFFSET) / SCALE)
    q = np.clip(q, 0, 254)
    return np.where(np.isfinite(db), q, NODATA).astype("uint8")


def nearest(dates: list[str], target: str) -> str:
    t = datetime.fromisoformat(target)
    return min(dates, key=lambda d: abs((datetime.fromisoformat(d) - t).days))


def export(raw: Path, web: Path, sid: str) -> dict:
    src = raw / sid
    info = json.loads((src / "stage.json").read_text())
    z = np.load(src / "cube.npz")
    dates = [str(d) for d in z["dates"]]
    pols = [p for p in ("HH", "HV") if f"blocks_{p}" in z.files]
    ny, nx = info["shape"]
    cube = np.stack([z[f"blocks_{p}"].astype("float32") for p in pols], axis=1)  # [T, P, ny, nx]
    t_n = cube.shape[0]
    blocks = quantize(cube.reshape(t_n, len(pols), ny * nx))
    dst = web / "stages" / sid
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "img").mkdir(parents=True)
    blocks.tofile(dst / "blocks.bin")
    files = info["render"]["files"]
    for name in files + ["img/thumb.webp"]:
        shutil.copy(src / name, dst / name)
    valid = np.isfinite(cube[:, 0]).sum(axis=0) >= max(2, t_n // 2)
    story = STORIES.get(sid, {})
    beats = [{"date": nearest(dates, b["date"]), "caption": b["caption"]}
             for b in story.get("beats", [])]
    moves = None
    mpath = src / "moves.npz"
    if mpath.exists():
        m = np.load(mpath)
        head = np.stack([m["move"].astype("uint8"), m["conf"].astype("uint8")], axis=1).ravel()
        per_beat = m["beat_move"].astype("uint8").ravel()  # [T, N]
        (dst / "moves.bin").write_bytes(head.tobytes() + per_beat.tobytes())
        moves = {"file": "moves.bin", "ids": MOVE_IDS, "layout": "N2 then TN",
                 "note": "First N*2 bytes: per block (move index, confidence 0-100). "
                         "Then T*N bytes: move index per beat (255 = none).",
                 "counts": {k: int(v) for k, v in json.loads(str(m["counts"])).items()}}
    highlight = story.get("highlight")
    hpath = src / "highlight.json"
    if hpath.exists():
        highlight = json.loads(hpath.read_text())
    stack = info["stack"]
    out = {
        "id": sid,
        "fixture": False,
        "name": info["spec"].get("name", sid),
        "country": info["spec"].get("country", ""),
        "bbox": info["spec"]["bbox"],
        "corners": info["corners"],
        "grid": {"nx": nx, "ny": ny, "res_m": 100, "epsg": info["grid"]["epsg"]},
        "stack": {"track": stack["track"], "direction": stack["direction"],
                  "bandwidth_mhz": stack["bandwidth_mhz"], "mode": stack["mode"],
                  "pols": pols, "crid": stack["crid"], "n_granules": len(info["metas"])},
        "dates": dates,
        "blocks": {"file": "blocks.bin", "encoding": "uint8", "scale": SCALE, "offset": OFFSET,
                   "nodata": NODATA, "layout": "TPN", "pols": pols},
        "images": {"res_m": info["img_res_m"], "nx": info["render"]["nx"],
                   "ny": info["render"]["ny"], "files": files, "thumb": "img/thumb.webp",
                   "stretch": info["render"]["stretch"]},
        "moves": moves,
        "story": {"title": story.get("title", info["spec"].get("name", sid)),
                  "lede": story.get("lede", ""), "body": story.get("body", []),
                  "beats": beats, "highlight": highlight},
        "sources": story.get("sources", []) + [
            {"name": "NISAR L2 GCOV, NASA-ISRO (ASF DAAC)",
             "url": "https://asf.alaska.edu/datasets/daac/nisar/"}],
        "stats": {"valid_blocks": int(valid.sum()), "km2": round(float(valid.sum()) / 100, 1)},
    }
    (dst / "stage.json").write_text(json.dumps(out, indent=1))
    return {
        "id": sid, "name": out["name"], "country": out["country"],
        "center": [round((out["bbox"][0] + out["bbox"][2]) / 2, 4),
                   round((out["bbox"][1] + out["bbox"][3]) / 2, 4)],
        "move": story.get("move", "still"), "title": out["story"]["title"],
        "teaser": story.get("teaser", ""), "n_passes": len(dates),
        "first": dates[0], "last": dates[-1], "thumb": f"{sid}/img/thumb.webp",
        "order": story.get("order", 99),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--web", type=Path, required=True)
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    ids = [s for s in args.only.split(",") if s] or sorted(
        p.name for p in args.raw.iterdir() if (p / "stage.json").exists())
    for sid in ids:
        print(json.dumps(export(args.raw, args.web, sid)))
    # index from every exported stage present
    entries = []
    for d in sorted((args.web / "stages").iterdir()):
        sj = d / "stage.json"
        if not sj.exists():
            continue
        s = json.loads(sj.read_text())
        story = STORIES.get(s["id"], {})
        entries.append({
            "id": s["id"], "name": s["name"], "country": s["country"],
            "center": [round((s["bbox"][0] + s["bbox"][2]) / 2, 4),
                       round((s["bbox"][1] + s["bbox"][3]) / 2, 4)],
            "move": story.get("move", "still"), "title": s["story"]["title"],
            "teaser": story.get("teaser", ""), "n_passes": len(s["dates"]),
            "first": s["dates"][0], "last": s["dates"][-1], "thumb": f"{s['id']}/img/thumb.webp",
            "order": story.get("order", 99),
        })
    entries.sort(key=lambda e: (e["order"], e["id"]))
    index = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"), "fixture": False,
             "stages": entries}
    (args.web / "stages" / "index.json").write_text(json.dumps(index, indent=1))
    print(f"index: {len(entries)} stages")


if __name__ == "__main__":
    main()

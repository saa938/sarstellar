"""Write a stage's web bundle (docs/v2/CONTRACT.md) from its raw outputs.

Raw directory layout (what `stage_job` and the live job write):
  stage.json   grid, corners, stack, dates, spec, render info
  cube.npz     blocks_<pol> [T, ny, nx] dB, dates
  img/NNN.webp radar false color per date, img/thumb.webp
  moves.npz    move, conf, beat_move [T, N], counts (optional)
  highlight.json (optional)
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import numpy as np

SCALE, OFFSET, NODATA = 0.2, -40.0, 255
MOVE_IDS = ["still", "fall", "scorch", "bounce", "vanish", "waltz", "shimmer", "melt"]


def quantize(db: np.ndarray) -> np.ndarray:
    q = np.clip(np.round((db.astype("float32") - OFFSET) / SCALE), 0, 254)
    return np.where(np.isfinite(db), q, NODATA).astype("uint8")


def nearest(dates: list[str], target: str) -> str:
    t = datetime.fromisoformat(target)
    return min(dates, key=lambda d: abs((datetime.fromisoformat(d) - t).days))


def write_bundle(src: Path, dst: Path, story: dict | None = None, sid: str | None = None) -> dict:
    """Write dst/{stage.json, blocks.bin, moves.bin?, img/*} and return the index entry."""
    story = story or {}
    info = json.loads((src / "stage.json").read_text())
    sid = sid or info["id"]
    z = np.load(src / "cube.npz")
    dates = [str(d) for d in z["dates"]]
    pols = [p for p in ("HH", "HV") if f"blocks_{p}" in z.files]
    ny, nx = info["shape"]
    cube = np.stack([z[f"blocks_{p}"].astype("float32") for p in pols], axis=1)
    t_n = cube.shape[0]
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "img").mkdir(parents=True)
    quantize(cube.reshape(t_n, len(pols), ny * nx)).tofile(dst / "blocks.bin")
    files = info["render"]["files"]
    for name in files + ["img/thumb.webp"]:
        shutil.copy(src / name, dst / name)
    valid = np.isfinite(cube[:, 0]).sum(axis=0) >= max(2, t_n // 2)
    moves = None
    if (src / "moves.npz").exists():
        m = np.load(src / "moves.npz")
        head = np.stack([m["move"].astype("uint8"), m["conf"].astype("uint8")], axis=1).ravel()
        per_beat = m["beat_move"].astype("uint8").ravel()
        (dst / "moves.bin").write_bytes(head.tobytes() + per_beat.tobytes())
        moves = {"file": "moves.bin", "ids": MOVE_IDS, "layout": "N2 then TN",
                 "note": "First N*2 bytes: per block (move index, confidence 0-100). "
                         "Then T*N bytes: move index per beat (255 = none).",
                 "counts": json.loads(str(m["counts"]))}
    highlight = story.get("highlight")
    if (src / "highlight.json").exists():
        highlight = json.loads((src / "highlight.json").read_text())
    beats = [{"date": nearest(dates, b["date"]), "caption": b["caption"]}
             for b in story.get("beats", [])]
    stack, spec = info["stack"], info.get("spec", {})
    out = {
        "id": sid, "fixture": False,
        "name": spec.get("name", sid), "country": spec.get("country", ""),
        "bbox": spec["bbox"], "corners": info["corners"],
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
        "story": {"title": story.get("title", spec.get("name", sid)), "lede": story.get("lede", ""),
                  "body": story.get("body", []), "beats": beats, "highlight": highlight},
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

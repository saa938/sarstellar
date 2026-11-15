#!/usr/bin/env python3
"""Synthetic constellation (stand-in for the science track's UMAP of every dance).

Reads the fixture stages in web/public/stages-fixture/ and writes
web/public/constellation-fixture.json + constellation-fixture.bin with the layout the web expects:
  planar: N x (x float32, y float32) in 0..1, then N uint8 move, then N uint8 stage index,
  then N uint32 block index (grid index n = row * nx + col), all little-endian.
Positions are a hand-made embedding (one cluster per move, spread by trajectory features), not UMAP.

Run from web/:  uv run --no-project --with numpy python scripts/make_constellation_fixture.py
"""

import json
import math
from pathlib import Path

import numpy as np

MOVE_IDS = ["still", "fall", "scorch", "bounce", "vanish", "waltz", "shimmer", "melt"]
CENTERS = {
    "still": (0.50, 0.50),
    "fall": (0.80, 0.30),
    "scorch": (0.86, 0.52),
    "bounce": (0.22, 0.24),
    "vanish": (0.16, 0.56),
    "waltz": (0.50, 0.84),
    "shimmer": (0.30, 0.80),
    "melt": (0.74, 0.80),
}


def main():
    web = Path(__file__).resolve().parent.parent
    root = web / "public" / "stages-fixture"
    index = json.loads((root / "index.json").read_text())
    rng = np.random.default_rng(5)
    xs, ys, mv, st, bl = [], [], [], [], []
    stage_ids = []
    for si, entry in enumerate(index["stages"]):
        sid = entry["id"]
        stage_ids.append(sid)
        meta = json.loads((root / sid / "stage.json").read_text())
        nx, ny = meta["grid"]["nx"], meta["grid"]["ny"]
        N = nx * ny
        T = len(meta["dates"])
        b = np.frombuffer((root / sid / "blocks.bin").read_bytes(), np.uint8).reshape(T, 2, N)
        valid = (b != 255).all(axis=(0, 1))
        db = -40.0 + 0.2 * b.astype(np.float32)
        hh, hv = db[:, 0, :], db[:, 1, :]
        moves = None
        if meta.get("moves"):
            mb = np.frombuffer((root / sid / "moves.bin").read_bytes(), np.uint8)
            moves = mb[: N * 2 : 2]
        idx = np.flatnonzero(valid)
        take = rng.choice(idx, size=min(22000, len(idx)), replace=False)
        f_dhv = hv[-2:, take].mean(0) - hv[:2, take].mean(0)
        f_amp = hv[:, take].max(0) - hv[:, take].min(0)
        f_hhpk = hh[:, take].max(0) - hh[:2, take].mean(0)
        f_dark = (hh[:, take] + hv[:, take]).min(0) - (hh[:2, take] + hv[:2, take]).mean(0)
        if moves is not None:
            m = moves[take].astype(int)
        else:
            m = np.zeros(len(take), int)
            m[f_dhv < -3] = MOVE_IDS.index("fall")
            m[(f_hhpk > 3) & (f_amp < 3)] = MOVE_IDS.index("bounce")
            m[f_dark < -8] = MOVE_IDS.index("vanish")
        for j, k in enumerate(take):
            mid = MOVE_IDS[m[j]] if m[j] < len(MOVE_IDS) else "still"
            cx, cy = CENTERS[mid]
            spread = 0.11 if mid == "still" else 0.055
            a = rng.uniform(0, 2 * math.pi)
            r = abs(rng.normal(0, spread))
            x = cx + math.cos(a) * r + 0.012 * f_dhv[j] + 0.006 * si
            y = cy + math.sin(a) * r * 0.8 + 0.008 * (f_amp[j] - 3) - 0.004 * si
            xs.append(x)
            ys.append(y)
            mv.append(m[j])
            st.append(si)
            bl.append(int(k))
    xs = np.array(xs, np.float32)
    ys = np.array(ys, np.float32)
    lo, hi = min(xs.min(), ys.min()), max(xs.max(), ys.max())
    xs = 0.03 + 0.94 * (xs - xs.min()) / (xs.max() - xs.min())
    ys = 0.03 + 0.94 * (ys - ys.min()) / (ys.max() - ys.min())
    n = len(xs)
    xy = np.stack([xs, ys], 1).astype("<f4").ravel()
    buf = xy.tobytes() + np.array(mv, np.uint8).tobytes() + np.array(st, np.uint8).tobytes() + np.array(bl, "<u4").tobytes()
    (web / "public" / "constellation-fixture.bin").write_bytes(buf)
    doc = {
        "fixture": True,
        "file": "constellation-fixture.bin",
        "count": n,
        "stages": stage_ids,
        "moves": MOVE_IDS,
        "layout": "planar: N x (x float32, y float32) in 0..1, then N uint8 move, then N uint8 stage index, then N uint32 block index; little-endian",
    }
    (web / "public" / "constellation-fixture.json").write_text(json.dumps(doc, indent=1))
    print(f"wrote {n} points ({len(buf)} bytes)")


if __name__ == "__main__":
    main()

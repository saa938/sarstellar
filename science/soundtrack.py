"""The demo video's soundtrack, generated from the stages' real NISAR data (no samples, no AI).

    python science/soundtrack.py --raw ../raw --out soundtrack.wav [--duration 28.4]

Scene timing follows web/src/pages/Present.tsx: globe 0-3 s, Punjab 3-9, Morton 9-13,
Edouard 13-17, Greenland 17-20, proof 20-25.5, end 25.5-28.
Each scene's plucks are its passes; pitch follows the measured backscatter (dB) quantized to an
A-minor pentatonic scale, so the melody rises with Punjab's wheat (HV) and rings higher as the
rice bounces (HH), falls with Morton's forest, and swings with Greenland's ice.
"""

from __future__ import annotations

import argparse
import wave
from pathlib import Path

import numpy as np

SR = 48000
SCALE = [0, 3, 5, 7, 10]  # A minor pentatonic intervals
A2 = 110.0


def note_freq(step: int) -> float:
    octave, idx = divmod(step, len(SCALE))
    return A2 * 2 ** (octave + SCALE[idx] / 12)


def db_to_step(v, lo, hi, steps=12, base=6):
    x = np.clip((v - lo) / max(hi - lo, 1e-6), 0, 1)
    return base + int(round(x * (steps - 1)))


def env(n, a=0.005, d=0.6, sr=SR):
    t = np.arange(n) / sr
    return np.minimum(1, t / a) * np.exp(-t / d)


def pluck(f, dur=1.4, amp=0.22, bright=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    tone = (np.sin(2 * np.pi * f * t) + 0.35 * bright * np.sin(2 * np.pi * 2 * f * t)
            + 0.12 * bright * np.sin(2 * np.pi * 3 * f * t))
    return amp * tone * env(n, d=0.45 + 0.25 / bright)


def bell(f, dur=2.5, amp=0.18):
    n = int(dur * SR)
    t = np.arange(n) / SR
    tone = (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * 2.76 * f * t) * np.exp(-t / 0.4)
            + 0.25 * np.sin(2 * np.pi * 5.4 * f * t) * np.exp(-t / 0.2))
    return amp * tone * env(n, a=0.002, d=0.9)


def pad(freqs, dur, amp=0.07):
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for f in freqs:
        for det in (-0.4, 0.4):
            out += np.sin(2 * np.pi * (f + det) * t + np.sin(2 * np.pi * 0.2 * t))
    a = np.minimum(1, t / 1.2) * np.minimum(1, (dur - t) / 1.2)
    return amp * out / (2 * len(freqs)) * np.clip(a, 0, 1)


def add(buf, sig, at):
    i = int(at * SR)
    j = min(len(buf), i + len(sig))
    if i < len(buf):
        buf[i:j] += sig[: j - i]


def medians(raw: Path, sid: str, sel: str):
    z = np.load(raw / sid / "cube.npz")
    m = np.load(raw / sid / "moves.npz")
    hh = z["blocks_HH"].astype("float32")
    t_n = hh.shape[0]
    H = hh.reshape(t_n, -1)
    V = z["blocks_HV"].astype("float32").reshape(t_n, -1) if "blocks_HV" in z.files else None
    ids = ["still", "fall", "scorch", "bounce", "vanish", "waltz", "shimmer", "melt"]
    pick = m["move"] == ids.index(sel)
    if pick.sum() < 50:
        pick = np.isfinite(H).all(0)
    with np.errstate(invalid="ignore"):
        h = np.nanmedian(H[:, pick], 1)
        v = np.nanmedian(V[:, pick], 1) if V is not None else None
    return h, v


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--duration", type=float, default=28.4)
    a = ap.parse_args()
    n = int(a.duration * SR)
    L = np.zeros(n)
    R = np.zeros(n)

    def place(sig, at, pan=0.0):
        add(L, sig * (1 - max(0, pan)), at)
        add(R, sig * (1 + min(0, pan)), at)

    # bed: Am9 -> Fmaj7 -> C -> G -> Am, slow
    chords = [(0, 3.0, [110, 164.8, 196, 246.9]), (3.0, 6.0, [87.3, 130.8, 174.6, 220]),
              (9.0, 4.0, [130.8, 164.8, 196, 261.6]), (13.0, 4.0, [98, 146.8, 196, 246.9]),
              (17.0, 3.0, [110, 164.8, 220, 261.6]), (20.0, 5.5, [87.3, 130.8, 174.6, 261.6]),
              (25.5, 2.9, [110, 164.8, 220, 329.6])]
    for at, dur, fr in chords:
        sig = pad(fr, dur + 1.0)
        place(sig, max(0, at - 0.5), pan=-0.15)
        place(sig * 0.8, max(0, at - 0.5), pan=0.15)

    # globe: a few sparse high notes, like stars
    for k, at in enumerate([0.6, 1.4, 2.1, 2.6]):
        place(bell(note_freq(14 + (k * 2) % 5), amp=0.08), at, pan=(-0.5 + k * 0.33))

    # Punjab: wheat in HV, rice in HH (24 passes over 6 s)
    h, v = medians(a.raw, "punjab", "waltz")
    t_n = len(h)
    for i in range(t_n):
        at = 3.0 + 6.0 * i / t_n
        place(pluck(note_freq(db_to_step(v[i], -21, -16, base=5)), amp=0.20), at, pan=-0.25)
        rise = h[i] - np.nanmin(h[: max(i, 1)]) if i else 0
        if h[i] > -8:  # rice standing in water: HH double bounce rings higher
            place(bell(note_freq(db_to_step(h[i], -9, -3, base=12)), dur=1.2, amp=0.10), at + 0.02, pan=0.35)

    # Morton: the forest falls (fall blocks, last 10 passes over 4 s)
    h, v = medians(a.raw, "morton", "fall")
    seq = v[-10:] if v is not None else h[-10:]
    for i, val in enumerate(seq):
        place(pluck(note_freq(db_to_step(val, -14, -9.5, base=6)), amp=0.2, bright=0.7),
              9.0 + 4.0 * i / len(seq), pan=-0.1)

    # Edouard: one pass, a bright chord where the forest bounces (~middle of the scene)
    for k, st in enumerate([10, 12, 14, 17]):
        place(bell(note_freq(st), dur=3.0, amp=0.12), 14.9 + 0.03 * k, pan=-0.3 + 0.2 * k)
    for i, at in enumerate([13.3, 13.9, 14.4]):
        place(pluck(note_freq(7 + i), amp=0.12), at)

    # Greenland: ice HH swings (10 passes over 3 s)
    h, _ = medians(a.raw, "greenland", "melt")
    for i in range(len(h)):
        place(bell(note_freq(db_to_step(h[i], -12.5, -5.5, base=9)), dur=1.6, amp=0.10),
              17.0 + 3.0 * i / len(h), pan=0.2)

    # proof: one soft bell per number
    for k, at in enumerate([20.6, 22.3, 24.0]):
        place(bell(note_freq(12 + 2 * k), dur=2.4, amp=0.12), at, pan=0)

    # end: resolve
    for k, st in enumerate([5, 8, 10, 12, 15]):
        place(bell(note_freq(st), dur=3.2, amp=0.07), 25.6 + 0.08 * k, pan=-0.4 + 0.2 * k)

    # gentle master: fade in/out, soft-clip, normalize to -1 dBFS peak
    t = np.arange(n) / SR
    fade = np.minimum(1, t / 0.4) * np.minimum(1, (a.duration - t) / 1.2)
    st = np.stack([L, R], 1) * fade[:, None]
    st = np.tanh(st * 1.4) / np.tanh(1.4)
    st = st / (np.abs(st).max() + 1e-9) * 0.89
    pcm = (st * 32767).astype("<i2")
    with wave.open(str(a.out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print(f"wrote {a.out} ({a.duration:.1f} s)")


if __name__ == "__main__":
    main()

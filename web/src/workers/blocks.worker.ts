/// <reference lib="webworker" />
// Decodes blocks.bin (uint8, layout TPN) and moves.bin into compact typed arrays off the main thread.
// Only blocks with at least one valid pass are kept (index k); gaps in time are filled with the
// nearest valid pass so dots never jump to the origin, and the original validity is kept for charts.

import type { DecodeRequest, DecodeResult } from "../stage/decoded";

const ctx = self as unknown as DedicatedWorkerGlobalScope;

ctx.onmessage = async (ev: MessageEvent<DecodeRequest>) => {
  const req = ev.data;
  try {
    const res = await fetch(req.url);
    if (!res.ok) throw new Error(`blocks.bin: HTTP ${res.status}`);
    const bytes = new Uint8Array(await res.arrayBuffer());
    let movesBytes: Uint8Array | null = null;
    if (req.movesUrl) {
      try {
        const r2 = await fetch(req.movesUrl);
        if (r2.ok) movesBytes = new Uint8Array(await r2.arrayBuffer());
      } catch {
        movesBytes = null;
      }
    }
    const out = decode(req, bytes, movesBytes);
    const transfer: Transferable[] = [out.idx.buffer, out.nToK.buffer, out.xy.buffer, out.valid.buffer, out.tint.buffer, out.zone.buffer, out.lonlat.buffer, out.medX.buffer, out.medY.buffer];
    if (out.move) transfer.push(out.move.buffer);
    if (out.conf) transfer.push(out.conf.buffer);
    if (out.beat) transfer.push(out.beat.buffer);
    ctx.postMessage({ ok: true, data: out }, transfer);
  } catch (err) {
    ctx.postMessage({ ok: false, error: String((err as Error)?.message || err) });
  }
};

function decode(req: DecodeRequest, b: Uint8Array, mb: Uint8Array | null): DecodeResult {
  const { T, P, nx, ny, scale, offset, nodata, corners, zones, zoneTints, hhOnly } = req;
  const N = nx * ny;
  if (b.length < T * P * N) throw new Error(`blocks.bin is ${b.length} bytes, expected ${T * P * N}`);

  // which blocks have any valid pass (all pols valid at that pass)
  const nToK = new Int32Array(N).fill(-1);
  let K = 0;
  for (let n = 0; n < N; n++) {
    let ok = false;
    for (let t = 0; t < T && !ok; t++) {
      let all = true;
      for (let p = 0; p < P; p++) if (b[(t * P + p) * N + n] === nodata) { all = false; break; }
      ok = all;
    }
    if (ok) nToK[n] = K++;
  }
  const idx = new Uint32Array(K);
  for (let n = 0; n < N; n++) if (nToK[n] >= 0) idx[nToK[n]] = n;

  const xy = new Float32Array(T * K * 2);
  const valid = new Uint8Array(T * K);
  const tint = new Uint8Array(K * 3);
  const zone = new Uint8Array(K);
  const lonlat = new Float32Array(K * 2);
  const vals = new Float32Array(T * 2);
  const vmask = new Uint8Array(T);

  const [tl, tr, br, bl] = corners;
  let seed = 1234567;
  const rand = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);

  for (let k = 0; k < K; k++) {
    const n = idx[k];
    for (let t = 0; t < T; t++) {
      let ok = true;
      for (let p = 0; p < P; p++) {
        const q = b[(t * P + p) * N + n];
        if (q === nodata) ok = false;
        vals[t * 2 + p] = offset + scale * q;
      }
      if (P === 1) vals[t * 2 + 1] = 0;
      vmask[t] = ok ? 1 : 0;
      valid[t * K + k] = ok ? 1 : 0;
    }
    // fill gaps: forward fill, then leading gaps take the first valid pass
    let last = -1;
    let firstValid = -1;
    for (let t = 0; t < T; t++) {
      if (vmask[t]) { last = t; if (firstValid < 0) firstValid = t; }
      else if (last >= 0) { vals[t * 2] = vals[last * 2]; vals[t * 2 + 1] = vals[last * 2 + 1]; }
    }
    for (let t = 0; t < firstValid; t++) { vals[t * 2] = vals[firstValid * 2]; vals[t * 2 + 1] = vals[firstValid * 2 + 1]; }
    if (hhOnly) {
      // one-partner floor: x = HH on the first pass (fixed), y = HH on this pass, so a dot only
      // moves up (louder than at the start) or down (quieter); the diagonal means no change
      const h0 = vals[0];
      for (let t = 0; t < T; t++) {
        vals[t * 2 + 1] = vals[t * 2];
        vals[t * 2] = h0;
      }
    }
    // de-quantization dither: one fixed offset per block inside its 0.2 dB bin, so the floor shows
    // no lattice and trajectories stay smooth (the offset never changes over time)
    const jx = (rand() - 0.5) * scale;
    const jy = (rand() - 0.5) * scale;
    for (let t = 0; t < T; t++) {
      xy[(t * K + k) * 2] = vals[t * 2] + jx;
      xy[(t * K + k) * 2 + 1] = vals[t * 2 + 1] + jy;
    }
    // starting zone from the first two passes
    const x0 = (vals[0] + vals[Math.min(1, T - 1) * 2]) / 2;
    const y0 = (vals[1] + vals[Math.min(1, T - 1) * 2 + 1]) / 2;
    let best = 0;
    let bd = Infinity;
    if (!hhOnly) {
      for (let z = 0; z < zones.length; z++) {
        const dx = x0 - zones[z].center[0];
        const dy = y0 - zones[z].center[1];
        const d = dx * dx + dy * dy;
        if (d < bd) { bd = d; best = z; }
      }
    }
    zone[k] = best;
    const c = hhOnly ? [190, 225, 255] : zoneTints[zones[best]?.id] || [230, 228, 220];
    const j = 0.82 + 0.18 * rand();
    tint[k * 3] = Math.min(255, c[0] * j);
    tint[k * 3 + 1] = Math.min(255, c[1] * j);
    tint[k * 3 + 2] = Math.min(255, c[2] * j);
    // block center lon/lat
    const row = Math.floor(n / nx);
    const col = n - row * nx;
    const u = (col + 0.5) / nx;
    const v = (row + 0.5) / ny;
    const topX = tl[0] + (tr[0] - tl[0]) * u;
    const topY = tl[1] + (tr[1] - tl[1]) * u;
    const botX = bl[0] + (br[0] - bl[0]) * u;
    const botY = bl[1] + (br[1] - bl[1]) * u;
    lonlat[k * 2] = topX + (botX - topX) * v;
    lonlat[k * 2 + 1] = topY + (botY - topY) * v;
  }

  // scene medians per pass (sampled) for context in charts
  const medX = new Float32Array(T);
  const medY = new Float32Array(T);
  const step = Math.max(1, Math.floor(K / 6000));
  const sx: number[] = [];
  const sy: number[] = [];
  for (let t = 0; t < T; t++) {
    sx.length = 0;
    sy.length = 0;
    for (let k = 0; k < K; k += step) {
      if (!valid[t * K + k]) continue;
      sx.push(xy[(t * K + k) * 2]);
      sy.push(xy[(t * K + k) * 2 + 1]);
    }
    medX[t] = median(sx);
    medY[t] = median(sy);
  }

  // value range for HH-only floors (1st to 99th percentile of every pass)
  let range: [number, number] | null = null;
  if (hhOnly) {
    const sample: number[] = [];
    const st = Math.max(1, Math.floor((T * K) / 40000));
    for (let i = 0; i < T * K; i += st) sample.push(xy[i * 2 + 1]);
    sample.sort((a, b) => a - b);
    const lo = sample[Math.floor(sample.length * 0.005)] ?? -25;
    const hi = sample[Math.floor(sample.length * 0.995)] ?? 0;
    range = [Math.floor(lo - 1.5), Math.ceil(hi + 1.5)];
  }

  let move: Uint8Array | null = null;
  let conf: Uint8Array | null = null;
  let beat: Uint8Array | null = null;
  let moveCounts: number[] | null = null;
  if (mb && mb.length >= N * 2) {
    move = new Uint8Array(K);
    conf = new Uint8Array(K);
    moveCounts = new Array(req.nMoves).fill(0);
    for (let k = 0; k < K; k++) {
      const n = idx[k];
      move[k] = mb[n * 2];
      conf[k] = mb[n * 2 + 1];
      if (move[k] < req.nMoves) moveCounts[move[k]]++;
    }
    if (mb.length >= N * 2 + T * N) {
      beat = new Uint8Array(T * K);
      for (let t = 0; t < T; t++) {
        const o = N * 2 + t * N;
        for (let k = 0; k < K; k++) beat[t * K + k] = mb[o + idx[k]];
      }
    }
  }

  return { K, T, nx, ny, idx, nToK, xy, valid, tint, zone, lonlat, medX, medY, move, conf, beat, moveCounts, range };
}

function median(a: number[]) {
  if (!a.length) return NaN;
  const s = a.slice().sort((x, y) => x - y);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

import type { DecodeResult } from "./decoded";
import type { Frame } from "./clock";

/** Interpolated floor position of every block at a frame (same easing as the GPU). */
export function positionsAt(d: DecodeResult, fr: Pick<Frame, "i0" | "i1" | "e">, out?: Float32Array) {
  const { K, xy } = d;
  const res = out && out.length === K * 2 ? out : new Float32Array(K * 2);
  const o0 = fr.i0 * K * 2;
  const o1 = fr.i1 * K * 2;
  const e = fr.e;
  for (let i = 0; i < K * 2; i++) {
    const a = xy[o0 + i];
    res[i] = a + (xy[o1 + i] - a) * e;
  }
  return res;
}

export function positionOf(d: DecodeResult, k: number, fr: Pick<Frame, "i0" | "i1" | "e">): [number, number] {
  const { K, xy } = d;
  const a = (fr.i0 * K + k) * 2;
  const b = (fr.i1 * K + k) * 2;
  return [xy[a] + (xy[b] - xy[a]) * fr.e, xy[a + 1] + (xy[b + 1] - xy[a + 1]) * fr.e];
}

export function pointInPolygon(x: number, y: number, poly: [number, number][]) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i][0];
    const yi = poly[i][1];
    const xj = poly[j][0];
    const yj = poly[j][1];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi + 1e-12) + xi) inside = !inside;
  }
  return inside;
}

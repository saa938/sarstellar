import type { LonLat } from "./types";

/** Bilinear position inside the stage quadrilateral (corners: TL, TR, BR, BL). */
export function quadPoint(c: [LonLat, LonLat, LonLat, LonLat], u: number, v: number): LonLat {
  const [tl, tr, br, bl] = c;
  const topX = tl[0] + (tr[0] - tl[0]) * u;
  const topY = tl[1] + (tr[1] - tl[1]) * u;
  const botX = bl[0] + (br[0] - bl[0]) * u;
  const botY = bl[1] + (br[1] - bl[1]) * u;
  return [topX + (botX - topX) * v, topY + (botY - topY) * v];
}

/** Inverse bilinear: lon/lat -> (u, v) in [0, 1] when inside. Newton iterations. */
export function quadInverse(c: [LonLat, LonLat, LonLat, LonLat], lon: number, lat: number): [number, number] {
  let u = 0.5;
  let v = 0.5;
  const [tl, tr, br, bl] = c;
  for (let i = 0; i < 8; i++) {
    const p = quadPoint(c, u, v);
    const fx = p[0] - lon;
    const fy = p[1] - lat;
    // partial derivatives
    const dux = (tr[0] - tl[0]) * (1 - v) + (br[0] - bl[0]) * v;
    const duy = (tr[1] - tl[1]) * (1 - v) + (br[1] - bl[1]) * v;
    const dvx = (bl[0] - tl[0]) * (1 - u) + (br[0] - tr[0]) * u;
    const dvy = (bl[1] - tl[1]) * (1 - u) + (br[1] - tr[1]) * u;
    const det = dux * dvy - dvx * duy;
    if (Math.abs(det) < 1e-18) break;
    const du = (fx * dvy - fy * dvx) / det;
    const dv = (dux * fy - duy * fx) / det;
    u -= du;
    v -= dv;
    if (Math.abs(du) < 1e-10 && Math.abs(dv) < 1e-10) break;
  }
  return [u, v];
}

/** Polygon (lon/lat ring) of one block. */
export function blockPolygon(c: [LonLat, LonLat, LonLat, LonLat], nx: number, ny: number, n: number): LonLat[] {
  const row = Math.floor(n / nx);
  const col = n % nx;
  const u0 = col / nx;
  const u1 = (col + 1) / nx;
  const v0 = row / ny;
  const v1 = (row + 1) / ny;
  const a = quadPoint(c, u0, v0);
  return [a, quadPoint(c, u1, v0), quadPoint(c, u1, v1), quadPoint(c, u0, v1), a];
}

export function formatLonLat(lon: number, lat: number) {
  const ns = lat >= 0 ? "N" : "S";
  const ew = lon >= 0 ? "E" : "W";
  return `${Math.abs(lat).toFixed(3)}°${ns} ${Math.abs(lon).toFixed(3)}°${ew}`;
}

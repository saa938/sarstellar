// Canvas 2D drawing for the HH vs HV chart. A static frame (regions, grid, axes) is rendered once
// per size into an offscreen canvas; animated frames blit it and draw points on top.

import { AXIS_X, AXIS_Y, REGIONS, REGION_TINT } from "../lib/labels";

export interface Range {
  xmin: number;
  xmax: number;
  ymin: number;
  ymax: number;
}

export const FLOOR: Range = { xmin: -30, xmax: 5, ymin: -38, ymax: -5 };

export interface Layout {
  W: number;
  H: number;
  x: number;
  y: number;
  w: number;
  h: number;
  compact: boolean;
}

export function layoutFor(W: number, H: number, compact: boolean): Layout {
  const ml = compact ? 34 : 50;
  const mr = compact ? 8 : 14;
  const mt = compact ? 8 : 10;
  const mb = compact ? 34 : 44;
  return { W, H, x: ml, y: mt, w: Math.max(10, W - ml - mr), h: Math.max(10, H - mt - mb), compact };
}

export const px = (L: Layout, r: Range, v: number) => L.x + ((v - r.xmin) / (r.xmax - r.xmin)) * L.w;
export const py = (L: Layout, r: Range, v: number) => L.y + ((r.ymax - v) / (r.ymax - r.ymin)) * L.h;

export function dpr() {
  return Math.min(window.devicePixelRatio || 1, 2);
}

export function sizeCanvas(c: HTMLCanvasElement, W: number, H: number) {
  const d = dpr();
  const w = Math.max(1, Math.round(W * d));
  const h = Math.max(1, Math.round(H * d));
  if (c.width !== w || c.height !== h) {
    c.width = w;
    c.height = h;
  }
  const ctx = c.getContext("2d")!;
  ctx.setTransform(d, 0, 0, d, 0, 0);
  return ctx;
}

const SERIF = '"Instrument Serif", Georgia, serif';
const SANS = '"Geist Variable", system-ui, sans-serif';
const MONO = '"Geist Mono Variable", ui-monospace, monospace';

/** Regions, grid, ticks and axis titles, rendered once per size. */
export function staticFrame(L: Layout, r: Range, opts: { regions?: boolean; labels?: boolean; hhOnlyY?: string; xTitle?: string; diagonal?: boolean } = {}) {
  const d = dpr();
  const c = document.createElement("canvas");
  c.width = Math.round(L.W * d);
  c.height = Math.round(L.H * d);
  const ctx = c.getContext("2d")!;
  ctx.setTransform(d, 0, 0, d, 0, 0);
  ctx.save();
  ctx.beginPath();
  ctx.rect(L.x, L.y, L.w, L.h);
  ctx.clip();
  if (opts.regions !== false) {
    const rad = Math.min(L.w, L.h) * 0.26;
    for (const z of REGIONS) {
      const cx = px(L, r, z.center[0]);
      const cy = py(L, r, z.center[1]);
      const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, rad);
      g.addColorStop(0, `rgba(${REGION_TINT[z.id]},0.22)`);
      g.addColorStop(1, `rgba(${REGION_TINT[z.id]},0)`);
      ctx.fillStyle = g;
      ctx.fillRect(cx - rad, cy - rad, rad * 2, rad * 2);
    }
  }
  ctx.strokeStyle = "rgba(255,255,255,0.05)";
  ctx.lineWidth = 1;
  for (let v = Math.ceil(r.xmin / 5) * 5; v <= r.xmax; v += 5) {
    const x = Math.round(px(L, r, v)) + 0.5;
    ctx.beginPath();
    ctx.moveTo(x, L.y);
    ctx.lineTo(x, L.y + L.h);
    ctx.stroke();
  }
  for (let v = Math.ceil(r.ymin / 5) * 5; v <= r.ymax; v += 5) {
    const y = Math.round(py(L, r, v)) + 0.5;
    ctx.beginPath();
    ctx.moveTo(L.x, y);
    ctx.lineTo(L.x + L.w, y);
    ctx.stroke();
  }
  if (opts.diagonal) {
    ctx.strokeStyle = "rgba(255,255,255,0.28)";
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(px(L, r, r.xmin), py(L, r, r.xmin));
    ctx.lineTo(px(L, r, r.xmax), py(L, r, r.xmax));
    ctx.stroke();
    ctx.setLineDash([]);
  }
  ctx.restore();
  ctx.strokeStyle = "rgba(255,255,255,0.1)";
  ctx.strokeRect(L.x + 0.5, L.y + 0.5, L.w - 1, L.h - 1);
  // ticks
  ctx.fillStyle = "rgba(239,237,230,0.38)";
  ctx.font = `${L.compact ? 9.5 : 10.5}px ${MONO}`;
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  for (let v = Math.ceil(r.xmin / 5) * 5; v <= r.xmax; v += 5) ctx.fillText(minus(v), px(L, r, v), L.y + L.h + 6);
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (let v = Math.ceil(r.ymin / 5) * 5; v <= r.ymax; v += 5) ctx.fillText(minus(v), L.x - 7, py(L, r, v));
  // axis titles
  ctx.fillStyle = "rgba(239,237,230,0.6)";
  ctx.font = `${L.compact ? 10.5 : 12}px ${SANS}`;
  ctx.textAlign = "right";
  ctx.textBaseline = "alphabetic";
  ctx.fillText(opts.xTitle ?? (L.compact ? "HH (dB) →" : `${AXIS_X} →`), L.x + L.w, L.y + L.h + (L.compact ? 30 : 38));
  ctx.save();
  ctx.translate(L.x - (L.compact ? 24 : 36), L.y);
  ctx.rotate(-Math.PI / 2);
  ctx.textAlign = "right";
  ctx.fillText(opts.hhOnlyY ?? (L.compact ? "HV (dB) →" : `${AXIS_Y} →`), 0, 0);
  ctx.restore();
  // region labels
  if (opts.labels !== false && opts.regions !== false) {
    ctx.font = `italic ${L.compact ? 13 : 16}px ${SERIF}`;
    ctx.fillStyle = "rgba(239,237,230,0.55)";
    for (const z of REGIONS) {
      let x = px(L, r, z.center[0]);
      let y = py(L, r, z.center[1]);
      const off = Math.min(L.w, L.h) * 0.075;
      ctx.textBaseline = "middle";
      ctx.textAlign = "center";
      if (z.pos === "above") y -= off;
      if (z.pos === "below") y += off;
      if (z.pos === "left") {
        x -= off * 0.9;
        ctx.textAlign = "right";
      }
      if (z.pos === "edge") {
        x = L.x + L.w - 8;
        y = py(L, r, z.center[1] + 4.2);
        ctx.textAlign = "right";
      }
      let text = z.label;
      if (L.compact && z.id === "bounce") text = "double bounce";
      ctx.fillText(text, x, y);
    }
  }
  return c;
}

function minus(v: number) {
  return v < 0 ? `−${Math.abs(v)}` : String(v);
}

const spriteCache = new Map<string, HTMLCanvasElement>();

/** A soft glowing dot, cached per color and size (device pixels). */
export function sprite(rgb: string, size: number) {
  const key = `${rgb}|${size}`;
  let s = spriteCache.get(key);
  if (s) return s;
  const n = Math.max(4, Math.ceil(size * 3));
  s = document.createElement("canvas");
  s.width = n;
  s.height = n;
  const ctx = s.getContext("2d")!;
  const g = ctx.createRadialGradient(n / 2, n / 2, 0, n / 2, n / 2, n / 2);
  g.addColorStop(0, `rgba(${rgb},1)`);
  g.addColorStop(0.22, `rgba(${rgb},0.75)`);
  g.addColorStop(0.5, `rgba(${rgb},0.16)`);
  g.addColorStop(1, `rgba(${rgb},0)`);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, n, n);
  spriteCache.set(key, s);
  return s;
}

export function hexRgb(hex: string) {
  const h = hex.replace("#", "");
  const n = parseInt(h, 16);
  return `${(n >> 16) & 255},${(n >> 8) & 255},${n & 255}`;
}

export function ease(f: number) {
  return f * f * f * (f * (f * 6 - 15) + 10);
}

export const reducedMotion = () => typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

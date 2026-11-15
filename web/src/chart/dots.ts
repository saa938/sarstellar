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
export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export type FrameCanvas = HTMLCanvasElement & { rects?: Rect[] };

/** Where region names sit (dB), chosen to fall in the empty space beside the diagonal cloud. */
const REGION_ANCHORS: { id: string; label: string; sub?: string; at: [number, number]; align: CanvasTextAlign }[] = [
  { id: "water", label: "open water", at: [-29.4, -36.6], align: "left" },
  { id: "soil", label: "bare soil", at: [-14.5, -33.5], align: "left" },
  { id: "crops", label: "crops", at: [-5, -27.5], align: "left" },
  { id: "forest", label: "forest", at: [-18, -9.5], align: "right" },
  { id: "bounce", label: "double bounce", sub: "cities, flooded trees, rice", at: [4.6, -6.4], align: "right" },
];

const overlaps = (a: Rect, b: Rect) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;

export interface Placed {
  x: number;
  y: number;
  align: CanvasTextAlign;
  box: Rect;
  leader: boolean;
}

/** Greedy label placement: the first spot near the point that stays inside the plot and touches no
 *  other text or marker; farther spots get a thin leader line. */
export function placeLabel(ctx: CanvasRenderingContext2D, L: Layout, x: number, y: number, text: string, font: string, occupied: Rect[]): Placed {
  ctx.font = font;
  const w = ctx.measureText(text).width;
  const h = parseFloat(font.match(/(\d+(?:\.\d+)?)px/)?.[1] ?? "14") + 4;
  const cands: [number, number][] = [
    [12, 0], [-12, 0], [10, -15], [10, 15], [-10, -15], [-10, 15],
    [24, -26], [24, 26], [-24, -26], [-24, 26], [40, 0], [-40, 0], [0, -32], [0, 32],
    [44, -40], [44, 40], [-44, -40], [-44, 40], [70, 0], [-70, 0],
  ];
  let best: Placed | null = null;
  let bestScore = Infinity;
  for (const [dx, dy] of cands) {
    const align: CanvasTextAlign = dx < 0 ? "right" : dx > 0 ? "left" : "center";
    const lx = x + dx;
    const ly = y + dy;
    const bx = align === "right" ? lx - w : align === "center" ? lx - w / 2 : lx;
    const box = { x: bx - 2, y: ly - h / 2, w: w + 4, h };
    const inside = box.x >= L.x + 2 && box.x + box.w <= L.x + L.w - 2 && box.y >= L.y + 2 && box.y + box.h <= L.y + L.h - 2;
    let score = inside ? 0 : 1000;
    for (const o of occupied) if (overlaps(box, o)) score += 100;
    score += Math.hypot(dx, dy) * 0.01;
    if (score < bestScore) {
      bestScore = score;
      best = { x: lx, y: ly, align, box, leader: Math.hypot(dx, dy) > 18 };
      if (score < 1) break;
    }
  }
  return best!;
}

/** A small rect around a marker, so labels keep clear of it. */
export const dotRect = (x: number, y: number, r = 6): Rect => ({ x: x - r, y: y - r, w: r * 2, h: r * 2 });

export function staticFrame(
  L: Layout,
  r: Range,
  opts: { regions?: boolean; labels?: boolean; hhOnlyY?: string; xTitle?: string; diagonal?: boolean; step?: number; labelMode?: "anchors" | "centers"; avoid?: Rect[] } = {},
): FrameCanvas {
  const step = opts.step ?? 5;
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
    const rad = Math.min(L.w / (r.xmax - r.xmin), L.h / (r.ymax - r.ymin)) * 9;
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
  for (let v = Math.ceil(r.xmin / step) * step; v <= r.xmax + 1e-9; v += step) {
    const x = Math.round(px(L, r, v)) + 0.5;
    ctx.beginPath();
    ctx.moveTo(x, L.y);
    ctx.lineTo(x, L.y + L.h);
    ctx.stroke();
  }
  for (let v = Math.ceil(r.ymin / step) * step; v <= r.ymax + 1e-9; v += step) {
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
  for (let v = Math.ceil(r.xmin / step) * step; v <= r.xmax + 1e-9; v += step) ctx.fillText(minus(Math.round(v)), px(L, r, v), L.y + L.h + 6);
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (let v = Math.ceil(r.ymin / step) * step; v <= r.ymax + 1e-9; v += step) ctx.fillText(minus(Math.round(v)), L.x - 7, py(L, r, v));
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
  // region labels: faint, pinned in the empty corners on either side of the diagonal cloud
  const rects: Rect[] = [];
  if (opts.labels !== false && opts.regions !== false) {
    const size = L.compact ? 13 : 15;
    ctx.font = `italic ${size}px ${SERIF}`;
    ctx.fillStyle = "rgba(239,237,230,0.42)";
    ctx.textBaseline = "middle";
    const centers = opts.labelMode === "centers";
    for (const a0 of REGION_ANCHORS) {
      const zc = REGIONS.find((z) => z.id === a0.id)!.center;
      const a = centers ? { ...a0, at: zc as [number, number], align: "center" as CanvasTextAlign, sub: undefined } : a0;
      if (centers && (a.at[0] < r.xmin + 0.5 || a.at[0] > r.xmax - 0.5 || a.at[1] < r.ymin + 0.5 || a.at[1] > r.ymax - 0.5)) continue;
      const x = Math.min(Math.max(px(L, r, a.at[0]), L.x + 6), L.x + L.w - 6);
      const y = Math.min(Math.max(py(L, r, a.at[1]), L.y + 10), L.y + L.h - 10);
      if (centers) {
        ctx.font = `italic ${size}px ${SERIF}`;
        const tw = ctx.measureText(a.label).width;
        const box = { x: x - tw / 2 - 2, y: y - size / 2 - 2, w: tw + 4, h: size + 4 };
        const inside = box.x > L.x && box.x + box.w < L.x + L.w && box.y > L.y && box.y + box.h < L.y + L.h;
        if (!inside || [...rects, ...(opts.avoid ?? [])].some((o) => overlaps(box, o))) continue;
      }
      ctx.textAlign = a.align;
      ctx.font = `italic ${size}px ${SERIF}`;
      const w = ctx.measureText(a.label).width;
      ctx.fillText(a.label, x, y);
      let h = size + 4;
      let wSub = 0;
      if (a.sub && !L.compact) {
        ctx.font = `${size - 4}px ${SANS}`;
        wSub = ctx.measureText(a.sub).width;
        ctx.fillText(a.sub, x, y + size - 1);
        h += size - 2;
      }
      const ww = Math.max(w, wSub);
      rects.push({ x: a.align === "right" ? x - ww : x, y: y - size / 2 - 2, w: ww, h });
    }
  }
  (c as FrameCanvas).rects = rects;
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

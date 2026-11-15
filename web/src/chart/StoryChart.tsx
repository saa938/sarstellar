import { useEffect, useMemo, useRef } from "react";
import { FLOOR, dotRect, ease, layoutFor, placeLabel, px, py, reducedMotion, sizeCanvas, sprite, staticFrame, type FrameCanvas, type Layout, type Placed, type Range, type Rect } from "./dots";
import type { PathPoint2 } from "../lib/story";
import { fmtDate } from "../lib/format";

export interface Mark {
  id: string;
  HH: number;
  HV: number;
  label: string;
}

interface Props {
  cloud?: number[][] | null;
  cloudTo?: number[][] | null;
  path?: PathPoint2[] | null;
  /** extra date to label on the path (the "after" pass), besides the first and last */
  afterDate?: string;
  marks?: Mark[];
  active?: string | null;
  morph?: boolean;
  /** zoom the axes to this chart's own data instead of the full floor */
  zoom?: boolean;
  ariaLabel: string;
}

// one cycle of the before -> after animation, in seconds
const HOLD0 = 1.0;
const MORPH = 2.6;
const HOLD1 = 2.6;
const BACK = 1.0;
const CYCLE = HOLD0 + MORPH + HOLD1 + BACK;

function phase(t: number) {
  const c = t % CYCLE;
  if (c < HOLD0) return 0;
  if (c < HOLD0 + MORPH) return ease((c - HOLD0) / MORPH);
  if (c < HOLD0 + MORPH + HOLD1) return 1;
  return 1 - ease((c - HOLD0 - MORPH - HOLD1) / BACK);
}

function pctile(a: number[], p: number) {
  if (!a.length) return NaN;
  const s = a.slice().sort((x, y) => x - y);
  return s[Math.min(s.length - 1, Math.max(0, Math.round(p * (s.length - 1))))];
}

/** Axes that frame this chart's data: 2nd-98th percentile of the clouds plus the whole path, padded 2 dB. */
function dataRange(cloud: number[][] | null | undefined, cloudTo: number[][] | null | undefined, path: PathPoint2[] | null | undefined): { r: Range; step: number } {
  const xs: number[] = [];
  const ys: number[] = [];
  for (const c of [cloud ?? [], cloudTo ?? []])
    for (const p of c) {
      xs.push(p[0]);
      ys.push(p[1]);
    }
  let x0 = pctile(xs, 0.02);
  let x1 = pctile(xs, 0.98);
  let y0 = pctile(ys, 0.02);
  let y1 = pctile(ys, 0.98);
  for (const p of path ?? []) {
    if (p.HV == null) continue;
    x0 = Math.min(x0, p.HH);
    x1 = Math.max(x1, p.HH);
    y0 = Math.min(y0, p.HV);
    y1 = Math.max(y1, p.HV);
  }
  if (!Number.isFinite(x0) || !Number.isFinite(y0)) return { r: FLOOR, step: 5 };
  x0 -= 2;
  x1 += 2;
  y0 -= 2;
  y1 += 2;
  const span = Math.max(x1 - x0, y1 - y0);
  const step = span <= 9 ? 1 : span <= 18 ? 2 : 5;
  return {
    r: { xmin: Math.floor(x0 / step) * step, xmax: Math.ceil(x1 / step) * step, ymin: Math.floor(y0 / step) * step, ymax: Math.ceil(y1 / step) * step },
    step,
  };
}

const SERIF = '"Instrument Serif", Georgia, serif';
const MONO = '"Geist Mono Variable", ui-monospace, monospace';

export function StoryChart({ cloud, cloudTo, path, afterDate, marks = [], active = null, morph = false, zoom = false, ariaLabel }: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const { r: range, step } = useMemo(() => (zoom ? dataRange(cloud, cloudTo, path) : { r: FLOOR, step: 5 }), [zoom, cloud, cloudTo, path]);
  const st = useRef({
    L: null as Layout | null,
    frame: null as FrameCanvas | null,
    visible: false,
    raf: 0,
    t0: 0,
    seen: 0,
    active,
    kick: () => {},
    markPlaced: [] as Placed[],
    datePlaced: [] as { i: number; text: string; p: Placed }[],
  });
  st.current.active = active;

  useEffect(() => {
    const el = wrap.current!;
    const c = canvas.current!;
    const S = st.current;
    const reduced = reducedMotion();
    const pathPts = (path ?? []).filter((p) => p.HV != null);

    const build = () => {
      const L = S.L!;
      const pts = pathPts.map((p) => [px(L, range, p.HH), py(L, range, p.HV as number)] as [number, number]);
      const pathRects: Rect[] = pts.map(([x, y]) => dotRect(x, y, 7));
      S.frame = staticFrame(L, range, zoom ? { step, labelMode: "centers", avoid: pathRects } : {});
      const ctx = c.getContext("2d")!;
      const occupied: Rect[] = [...(S.frame.rects ?? []), ...pathRects];
      const markPts = marks.map((m) => [px(L, range, m.HH), py(L, range, m.HV)] as [number, number]);
      for (const [x, y] of markPts) occupied.push(dotRect(x, y, 8));
      S.markPlaced = marks.map((m, i) => {
        const p = placeLabel(ctx, L, markPts[i][0], markPts[i][1], m.label, `italic ${L.compact ? 14 : 17}px ${SERIF}`, occupied);
        occupied.push(p.box);
        return p;
      });
      // dates: first and last points of the path, plus the "after" pass if it is another point
      const want = new Set<number>();
      if (pts.length) {
        want.add(0);
        want.add(pts.length - 1);
        if (afterDate) {
          const j = pathPts.findIndex((p) => p.date === afterDate);
          if (j >= 0) want.add(j);
        }
      }
      S.datePlaced = [...want]
        .sort((a, b) => a - b)
        .map((i) => {
          const text = fmtDate(pathPts[i].date);
          const p = placeLabel(ctx, L, pts[i][0], pts[i][1], text, `${L.compact ? 10 : 11}px ${MONO}`, occupied);
          occupied.push(p.box);
          return { i, text, p };
        });
    };

    const label = (ctx: CanvasRenderingContext2D, x: number, y: number, p: Placed, text: string, font: string, color: string) => {
      if (p.leader) {
        ctx.strokeStyle = "rgba(247,227,181,0.45)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, y);
        const tx = p.align === "right" ? p.box.x + p.box.w : p.align === "left" ? p.box.x : p.box.x + p.box.w / 2;
        ctx.lineTo(tx, p.y);
        ctx.stroke();
      }
      ctx.font = font;
      ctx.textAlign = p.align;
      ctx.textBaseline = "middle";
      // a dark halo keeps labels legible over the bright cloud
      ctx.lineJoin = "round";
      ctx.lineWidth = 4;
      ctx.strokeStyle = "rgba(6,7,11,0.82)";
      ctx.strokeText(text, p.x, p.y);
      ctx.fillStyle = color;
      ctx.fillText(text, p.x, p.y);
    };

    const draw = (now: number) => {
      const L = S.L;
      if (!L || !S.frame) return;
      const ctx = sizeCanvas(c, L.W, L.H);
      ctx.clearRect(0, 0, L.W, L.H);
      ctx.drawImage(S.frame, 0, 0, L.W, L.H);
      const t = morph ? (reduced ? 1 : phase((now - S.t0) / 1000)) : 1;
      const d = Math.min(window.devicePixelRatio || 1, 2);
      ctx.save();
      ctx.beginPath();
      ctx.rect(L.x, L.y, L.w, L.h);
      ctx.clip();
      ctx.globalCompositeOperation = "lighter";
      const dot = sprite("214,222,240", Math.round((L.compact ? 2.6 : 3.2) * d));
      const ds = dot.width / d;
      const drawCloud = (pts: number[][], alpha: number, other?: number[][] | null, f = 0) => {
        ctx.globalAlpha = alpha;
        for (let i = 0; i < pts.length; i++) {
          let x = pts[i][0];
          let y = pts[i][1];
          if (other && other[i]) {
            x += (other[i][0] - x) * f;
            y += (other[i][1] - y) * f;
          }
          ctx.drawImage(dot, px(L, range, x) - ds / 2, py(L, range, y) - ds / 2, ds, ds);
        }
      };
      const base = Math.min(0.42, Math.max(0.05, (zoom ? 7.5 : 5.2) / Math.sqrt((cloud?.length ?? 1) + 1)));
      if (cloud && cloudTo && cloudTo.length === cloud.length) drawCloud(cloud, base, cloudTo, t);
      else {
        if (cloud) drawCloud(cloud, base * (cloudTo ? 1 - t : 1));
        if (cloudTo) drawCloud(cloudTo, base * t);
      }
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";
      // the median path, drawn as far as the animation has reached, with an arrowhead at its tip
      if (pathPts.length > 1) {
        const pts = pathPts.map((p) => [px(L, range, p.HH), py(L, range, p.HV as number)] as [number, number]);
        const reach = t * (pts.length - 1);
        ctx.strokeStyle = "rgba(247,227,181,0.95)";
        ctx.lineWidth = 2.2;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(pts[0][0], pts[0][1]);
        let head = pts[0];
        let prev = pts[0];
        for (let i = 1; i < pts.length; i++) {
          if (i <= reach) {
            ctx.lineTo(pts[i][0], pts[i][1]);
            prev = pts[i - 1];
            head = pts[i];
          } else {
            const f = reach - (i - 1);
            if (f > 0) {
              prev = pts[i - 1];
              head = [pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * f, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * f];
              ctx.lineTo(head[0], head[1]);
            }
            break;
          }
        }
        ctx.stroke();
        ctx.fillStyle = "#f7e3b5";
        pts.forEach((p, i) => {
          if (i > reach + 1e-6 || i === pts.length - 1) return;
          ctx.beginPath();
          ctx.arc(p[0], p[1], 3, 0, Math.PI * 2);
          ctx.fill();
        });
        const ang = Math.atan2(head[1] - prev[1], head[0] - prev[0]);
        if (Math.hypot(head[0] - prev[0], head[1] - prev[1]) > 0.5) {
          const a = 11;
          ctx.beginPath();
          ctx.moveTo(head[0] + Math.cos(ang) * 3, head[1] + Math.sin(ang) * 3);
          ctx.lineTo(head[0] - Math.cos(ang - 0.45) * a, head[1] - Math.sin(ang - 0.45) * a);
          ctx.lineTo(head[0] - Math.cos(ang + 0.45) * a, head[1] - Math.sin(ang + 0.45) * a);
          ctx.closePath();
          ctx.fill();
        }
        const glow = sprite("242,208,138", Math.round(16 * d));
        const gs = glow.width / d;
        ctx.globalCompositeOperation = "lighter";
        ctx.drawImage(glow, head[0] - gs / 2, head[1] - gs / 2, gs, gs);
        ctx.globalCompositeOperation = "source-over";
        for (const dl of S.datePlaced) {
          if (dl.i > reach + 1e-6) continue;
          label(ctx, pts[dl.i][0], pts[dl.i][1], dl.p, dl.text, `${L.compact ? 10 : 11}px ${MONO}`, "rgba(247,227,181,0.92)");
        }
      }
      // labeled marks, revealed one by one the first time the chart is seen
      if (marks.length) {
        const since = S.seen ? (now - S.seen) / 1000 : 0;
        const big = sprite("242,208,138", Math.round(16 * d));
        const bs = big.width / d;
        marks.forEach((m, i) => {
          const a = reduced ? 1 : Math.min(1, Math.max(0, (since - i * 0.32) / 0.4));
          if (a <= 0) return;
          const x = px(L, range, m.HH);
          const y = py(L, range, m.HV);
          const on = S.active === m.id;
          ctx.globalAlpha = a;
          const z = bs * (on ? 1.5 : 1);
          ctx.globalCompositeOperation = "lighter";
          ctx.drawImage(big, x - z / 2, y - z / 2, z, z);
          ctx.globalCompositeOperation = "source-over";
          ctx.fillStyle = "#fff8e8";
          ctx.beginPath();
          ctx.arc(x, y, on ? 5 : 3.6, 0, Math.PI * 2);
          ctx.fill();
          if (on) {
            ctx.strokeStyle = "rgba(247,227,181,0.9)";
            ctx.lineWidth = 1.4;
            ctx.beginPath();
            ctx.arc(x, y, 11, 0, Math.PI * 2);
            ctx.stroke();
          }
          const p = S.markPlaced[i];
          if (p) label(ctx, x, y, p, m.label, `${on ? "" : "italic "}${L.compact ? 14 : 17}px ${SERIF}`, on ? "#fff8e8" : "rgba(247,227,181,0.95)");
        });
        ctx.globalAlpha = 1;
      }
      ctx.restore();
    };

    const loop = (now: number) => {
      S.raf = 0;
      draw(now);
      const revealing = marks.length && S.seen && (now - S.seen) / 1000 < marks.length * 0.32 + 0.5;
      if (S.visible && !reduced && (morph || revealing)) S.raf = requestAnimationFrame(loop);
    };
    const kick = () => {
      if (!S.raf) S.raf = requestAnimationFrame(loop);
    };
    S.kick = kick;

    const ro = new ResizeObserver(() => {
      if (!wrap.current) return;
      const r = el.getBoundingClientRect();
      if (r.width < 2) return;
      S.L = layoutFor(r.width, r.height, r.width < 460);
      build();
      kick();
    });
    ro.observe(el);
    const io = new IntersectionObserver(
      ([e]) => {
        S.visible = e.isIntersecting;
        if (S.visible) {
          if (!S.t0) S.t0 = performance.now();
          if (!S.seen) S.seen = performance.now();
          kick();
        }
      },
      { threshold: 0.15 },
    );
    io.observe(el);
    document.fonts?.ready.then(() => {
      if (S.L && wrap.current) {
        build();
        kick();
      }
    });
    return () => {
      ro.disconnect();
      io.disconnect();
      cancelAnimationFrame(S.raf);
      S.raf = 0;
    };
  }, [cloud, cloudTo, path, marks, morph, zoom, range, step, afterDate]);

  useEffect(() => {
    st.current.kick();
  }, [active]);

  return (
    <div ref={wrap} className="dchart" role="img" aria-label={ariaLabel}>
      <canvas ref={canvas} />
    </div>
  );
}

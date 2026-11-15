import { useEffect, useRef } from "react";
import { FLOOR, ease, layoutFor, px, py, reducedMotion, sizeCanvas, sprite, staticFrame, type Layout } from "./dots";
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
  marks?: Mark[];
  active?: string | null;
  morph?: boolean;
  ariaLabel: string;
}

// one cycle of the before -> after animation, in seconds
const HOLD0 = 0.9;
const MORPH = 2.8;
const HOLD1 = 2.8;
const BACK = 1.1;
const CYCLE = HOLD0 + MORPH + HOLD1 + BACK;

function phase(t: number) {
  const c = t % CYCLE;
  if (c < HOLD0) return 0;
  if (c < HOLD0 + MORPH) return ease((c - HOLD0) / MORPH);
  if (c < HOLD0 + MORPH + HOLD1) return 1;
  return 1 - ease((c - HOLD0 - MORPH - HOLD1) / BACK);
}

export function StoryChart({ cloud, cloudTo, path, marks = [], active = null, morph = false, ariaLabel }: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const st = useRef({ L: null as Layout | null, frame: null as HTMLCanvasElement | null, visible: false, raf: 0, t0: 0, seen: 0, active, kick: () => {} });
  st.current.active = active;

  useEffect(() => {
    const el = wrap.current!;
    const c = canvas.current!;
    const S = st.current;
    const reduced = reducedMotion();

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
      // the faint cloud of hectares
      const dot = sprite("214,222,240", Math.round((L.compact ? 2.4 : 3) * d));
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
          ctx.drawImage(dot, px(L, FLOOR, x) - ds / 2, py(L, FLOOR, y) - ds / 2, ds, ds);
        }
      };
      const base = Math.min(0.42, Math.max(0.05, 5.2 / Math.sqrt((cloud?.length ?? 1) + 1)));
      if (cloud && cloudTo && cloudTo.length === cloud.length) drawCloud(cloud, base, cloudTo, t);
      else {
        if (cloud) drawCloud(cloud, base * (cloudTo ? 1 - t : 1));
        if (cloudTo) drawCloud(cloudTo, base * t);
      }
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";
      // the median path, drawn as far as the animation has reached
      if (path && path.length > 1) {
        const pts = path.filter((p) => p.HV != null).map((p) => [px(L, FLOOR, p.HH), py(L, FLOOR, p.HV as number)] as [number, number]);
        const reach = t * (pts.length - 1);
        ctx.strokeStyle = "rgba(247,227,181,0.9)";
        ctx.lineWidth = 2;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(pts[0][0], pts[0][1]);
        let head = pts[0];
        for (let i = 1; i < pts.length; i++) {
          if (i <= reach) {
            ctx.lineTo(pts[i][0], pts[i][1]);
            head = pts[i];
          } else {
            const f = reach - (i - 1);
            if (f > 0) {
              head = [pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * f, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * f];
              ctx.lineTo(head[0], head[1]);
            }
            break;
          }
        }
        ctx.stroke();
        ctx.fillStyle = "#f7e3b5";
        pts.forEach((p, i) => {
          if (i > reach + 1e-6) return;
          ctx.beginPath();
          ctx.arc(p[0], p[1], 3, 0, Math.PI * 2);
          ctx.fill();
        });
        const glow = sprite("242,208,138", Math.round(14 * d));
        const gs = glow.width / d;
        ctx.globalCompositeOperation = "lighter";
        ctx.drawImage(glow, head[0] - gs / 2, head[1] - gs / 2, gs, gs);
        ctx.globalCompositeOperation = "source-over";
        // date labels on the first and last points
        ctx.font = `${L.compact ? 10 : 11}px "Geist Mono Variable", ui-monospace, monospace`;
        ctx.fillStyle = "rgba(247,227,181,0.85)";
        ctx.textBaseline = "middle";
        const first = path.find((p) => p.HV != null)!;
        const last = [...path].reverse().find((p) => p.HV != null)!;
        // first date below-left of its point, last date above-right, so they never collide
        ctx.textAlign = "right";
        ctx.fillText(fmtDate(first.date), pts[0][0] - 8, pts[0][1] + 13);
        if (reach >= pts.length - 1 - 1e-6) {
          ctx.textAlign = "left";
          ctx.fillText(fmtDate(last.date), pts[pts.length - 1][0] + 8, pts[pts.length - 1][1] - 13);
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
          const x = px(L, FLOOR, m.HH);
          const y = py(L, FLOOR, m.HV);
          const on = S.active === m.id;
          ctx.globalAlpha = a;
          ctx.globalCompositeOperation = "lighter";
          ctx.drawImage(big, x - (bs * (on ? 1.5 : 1)) / 2, y - (bs * (on ? 1.5 : 1)) / 2, bs * (on ? 1.5 : 1), bs * (on ? 1.5 : 1));
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
          ctx.font = `${on ? "" : "italic "}${L.compact ? 14 : 17}px "Instrument Serif", Georgia, serif`;
          ctx.fillStyle = on ? "#fff8e8" : "rgba(247,227,181,0.92)";
          ctx.textBaseline = "middle";
          const right = x > L.x + L.w * 0.72;
          ctx.textAlign = right ? "right" : "left";
          ctx.fillText(m.label, x + (right ? -12 : 12), y - 1);
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
      S.frame = staticFrame(S.L, FLOOR);
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
        S.frame = staticFrame(S.L, FLOOR);
        kick();
      }
    });
    return () => {
      ro.disconnect();
      io.disconnect();
      cancelAnimationFrame(S.raf);
      S.raf = 0;
    };
  }, [cloud, cloudTo, path, marks, morph]);

  // redraw once when the active mark changes
  useEffect(() => {
    st.current.kick();
  }, [active]);

  return (
    <div ref={wrap} className="dchart" role="img" aria-label={ariaLabel}>
      <canvas ref={canvas} />
    </div>
  );
}

import { useEffect, useRef } from "react";
import { FLOOR, hexRgb, layoutFor, px, py, sizeCanvas, sprite, staticFrame, type Layout, type Range } from "./dots";
import type { DecodeResult } from "../stage/decoded";
import type { Clock, Frame } from "../stage/clock";
import { CHANGE_COLOR } from "../lib/labels";

interface Props {
  data: DecodeResult;
  sample: Int32Array;
  moveIds: string[] | null;
  paths: number[];
  clock: Clock;
  hhOnly: boolean;
  selected: number | null;
  onPick: (k: number | null) => void;
}

/** The sampled hectares of one place at the current pass, synced to the time-lapse clock. */
export function PlaceChart({ data, sample, moveIds, paths, clock, hhOnly, selected, onPick }: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const st = useRef({ L: null as Layout | null, frame: null as HTMLCanvasElement | null, visible: true, fr: clock.frame() as Frame, selected, pos: new Float32Array(sample.length * 2) });
  st.current.selected = selected;
  const range: Range = hhOnly && data.range ? { xmin: data.range[0], xmax: data.range[1], ymin: data.range[0], ymax: data.range[1] } : FLOOR;

  useEffect(() => {
    const el = wrap.current!;
    const c = canvas.current!;
    const S = st.current;
    const d = Math.min(window.devicePixelRatio || 1, 2);
    const groups = new Map<string, number[]>();
    for (let j = 0; j < sample.length; j++) {
      const k = sample[j];
      const m = data.move && moveIds ? moveIds[data.move[k]] ?? "still" : "still";
      const g = groups.get(m) ?? [];
      g.push(j);
      groups.set(m, g);
    }
    const K = data.K;
    const at = (t: number, k: number) => [data.xy[(t * K + k) * 2], data.xy[(t * K + k) * 2 + 1]];
    const draw = () => {
      const L = S.L;
      if (!L || !S.frame || !S.visible) return;
      const fr = S.fr;
      const ctx = sizeCanvas(c, L.W, L.H);
      ctx.clearRect(0, 0, L.W, L.H);
      ctx.drawImage(S.frame, 0, 0, L.W, L.H);
      ctx.save();
      ctx.beginPath();
      ctx.rect(L.x, L.y, L.w, L.h);
      ctx.clip();
      // positions at this moment
      const o0 = fr.i0 * K * 2;
      const o1 = fr.i1 * K * 2;
      for (let j = 0; j < sample.length; j++) {
        const k = sample[j] * 2;
        const x0 = data.xy[o0 + k];
        const y0 = data.xy[o0 + k + 1];
        S.pos[j * 2] = x0 + (data.xy[o1 + k] - x0) * fr.e;
        S.pos[j * 2 + 1] = y0 + (data.xy[o1 + k + 1] - y0) * fr.e;
      }
      ctx.globalCompositeOperation = "lighter";
      const sz = Math.round((L.compact ? 2.6 : 3.2) * d);
      for (const [m, js] of groups) {
        const spr = sprite(hexRgb(CHANGE_COLOR[m] ?? "#b9bccb"), sz);
        const s = spr.width / d;
        ctx.globalAlpha = m === "still" ? 0.42 : 0.85;
        for (const j of js) ctx.drawImage(spr, px(L, range, S.pos[j * 2]) - s / 2, py(L, range, S.pos[j * 2 + 1]) - s / 2, s, s);
      }
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";
      // highlighted hectares: their whole path, bright up to now
      const head = fr.i0 + fr.e;
      for (const k of paths) {
        ctx.lineWidth = 1.4;
        ctx.strokeStyle = "rgba(247,227,181,0.22)";
        ctx.beginPath();
        for (let t = 0; t < data.T; t++) {
          const [x, y] = at(t, k);
          if (t === 0) ctx.moveTo(px(L, range, x), py(L, range, y));
          else ctx.lineTo(px(L, range, x), py(L, range, y));
        }
        ctx.stroke();
        ctx.strokeStyle = "rgba(247,227,181,0.9)";
        ctx.beginPath();
        for (let t = 0; t <= Math.min(data.T - 1, Math.ceil(head)); t++) {
          let [x, y] = at(t, k);
          if (t > head) {
            const [xa, ya] = at(t - 1, k);
            const f = head - (t - 1);
            x = xa + (x - xa) * f;
            y = ya + (y - ya) * f;
          }
          if (t === 0) ctx.moveTo(px(L, range, x), py(L, range, y));
          else ctx.lineTo(px(L, range, x), py(L, range, y));
        }
        ctx.stroke();
      }
      // the selected hectare
      if (S.selected != null) {
        const k = S.selected;
        const a = at(fr.i0, k);
        const b = at(fr.i1, k);
        const x = px(L, range, a[0] + (b[0] - a[0]) * fr.e);
        const y = py(L, range, a[1] + (b[1] - a[1]) * fr.e);
        ctx.strokeStyle = "#f7e3b5";
        ctx.lineWidth = 1.8;
        ctx.beginPath();
        ctx.arc(x, y, 8, 0, Math.PI * 2);
        ctx.stroke();
        ctx.fillStyle = "#fff8e8";
        ctx.beginPath();
        ctx.arc(x, y, 3, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();
    };
    const unsub = clock.subscribe((fr) => {
      S.fr = fr;
      draw();
    });
    const ro = new ResizeObserver(() => {
      if (!wrap.current) return;
      const r = el.getBoundingClientRect();
      if (r.width < 2) return;
      S.L = layoutFor(r.width, r.height, r.width < 460);
      S.frame = staticFrame(S.L, range, hhOnly ? { regions: false, xTitle: "HH on the first pass (dB) →", hhOnlyY: "HH on this pass (dB) →", diagonal: true } : {});
      draw();
    });
    ro.observe(el);
    const io = new IntersectionObserver(([e]) => {
      S.visible = e.isIntersecting;
      if (S.visible) draw();
    });
    io.observe(el);
    document.fonts?.ready.then(() => {
      if (S.L && wrap.current) {
        S.frame = staticFrame(S.L, range, hhOnly ? { regions: false, xTitle: "HH on the first pass (dB) →", hhOnlyY: "HH on this pass (dB) →", diagonal: true } : {});
        draw();
      }
    });
    (S as unknown as { draw: () => void }).draw = draw;
    return () => {
      unsub();
      ro.disconnect();
      io.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, sample, moveIds, paths, clock, hhOnly]);

  useEffect(() => {
    (st.current as unknown as { draw?: () => void }).draw?.();
  }, [selected]);

  const onClick = (e: React.MouseEvent) => {
    const S = st.current;
    const L = S.L;
    if (!L || !wrap.current) return;
    const r = wrap.current.getBoundingClientRect();
    const mx = e.clientX - r.left;
    const my = e.clientY - r.top;
    let best = -1;
    let bd = 14 * 14;
    for (let j = 0; j < sample.length; j++) {
      const dx = px(L, range, S.pos[j * 2]) - mx;
      const dy = py(L, range, S.pos[j * 2 + 1]) - my;
      const dd = dx * dx + dy * dy;
      if (dd < bd) {
        bd = dd;
        best = j;
      }
    }
    onPick(best >= 0 ? sample[best] : null);
  };

  return (
    <div ref={wrap} className="dchart dchart--place" onClick={onClick} role="img" aria-label="Every sampled hectare placed by its two echoes at this pass. Click one to see its history.">
      <canvas ref={canvas} />
    </div>
  );
}

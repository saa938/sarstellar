import { useEffect, useMemo, useRef, useState } from "react";
import { Nav } from "../components/Nav";
import { FixtureTag } from "../components/FixtureTag";
import { loadConstellation, loadIndex, type Constellation as C, type IndexResult } from "../lib/data";
import { MOVE_COLORS, MOVE_IDS, MOVE_NAMES, hexToRgb, lighten } from "../lib/moves";
import { FloorGL, type FloorView } from "../stage/floorGL";
import { fmtInt } from "../lib/format";

// on wide screens, shift the sky right so the stars clear the panel on the left
const SHIFT = typeof window !== "undefined" && window.innerWidth > 900 ? 0.17 : 0;
const FULL: FloorView = { xmin: -0.02 - SHIFT, xmax: 1.02 - SHIFT, ymin: -0.02, ymax: 1.02 };

export default function Constellation() {
  const [c, setC] = useState<C | null | undefined>(undefined);
  const [idx, setIdx] = useState<IndexResult | null>(null);
  const [onlyMove, setOnlyMove] = useState<number | null>(null);
  const [onlyStage, setOnlyStage] = useState<number | null>(null);
  const [hover, setHover] = useState<{ i: number; x: number; y: number } | null>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const glRef = useRef<FloorGL | null>(null);
  const viewRef = useRef<FloorView>({ ...FULL });
  const sizeRef = useRef({ w: 1, h: 1 });
  const hoverRef = useRef(-1);

  useEffect(() => {
    loadConstellation().then(setC);
    loadIndex().then(setIdx);
  }, []);

  const moveIds = c?.doc.moves ?? [...MOVE_IDS];
  const counts = useMemo(() => {
    if (!c) return [];
    const n = new Array(moveIds.length).fill(0);
    for (let i = 0; i < c.N; i++) if (c.move[i] < n.length) n[c.move[i]]++;
    return n;
  }, [c, moveIds.length]);

  const stageName = (si: number) => {
    const id = c?.doc.stages[si];
    return idx?.index.stages.find((s) => s.id === id)?.name ?? (id ? id.replace(/-/g, " ").replace(/\b\w/g, (ch) => ch.toUpperCase()) : "?");
  };

  const draw = () => {
    const gl = glRef.current;
    if (!gl || !c) return;
    const { w, h } = sizeRef.current;
    const per = (w * h) / Math.max(1, c.N);
    gl.draw({
      i0: 0,
      i1: 0,
      e: 0,
      head: 0,
      view: aspectView(viewRef.current, w, h),
      selActive: onlyMove != null || onlyStage != null,
      pointPx: Math.min(3.2, Math.max(1.6, Math.sqrt(per) * 1.1)),
      gain: Math.min(0.9, Math.max(0.16, 0.5 * Math.sqrt(per / 3.5))),
      exposure: 1.05,
      dimOthers: 0.08,
      hoverK: hoverRef.current,
    });
  };
  const drawRef = useRef(draw);
  drawRef.current = draw;

  // GL setup + data
  useEffect(() => {
    if (!canvas.current || !c) return;
    const gl = new FloorGL(canvas.current);
    glRef.current = gl;
    gl.setData(c.xy, 1, c.N);
    const ro = new ResizeObserver(() => {
      if (!wrap.current || glRef.current !== gl) return;
      const r = wrap.current.getBoundingClientRect();
      sizeRef.current = { w: r.width, h: r.height };
      gl.resize(r.width, r.height, Math.min(window.devicePixelRatio || 1, 2));
      drawRef.current();
    });
    ro.observe(wrap.current!);
    return () => {
      ro.disconnect();
      gl.destroy();
      glRef.current = null;
    };
  }, [c]);

  // colors and filters
  useEffect(() => {
    const gl = glRef.current;
    if (!gl || !c) return;
    const rgb = moveIds.map((m) => (m === "still" ? ([196, 200, 214] as [number, number, number]) : lighten(hexToRgb(MOVE_COLORS[m] ?? "#999"), 0.15)));
    const out = new Uint8Array(c.N * 4);
    for (let i = 0; i < c.N; i++) {
      const col = rgb[c.move[i]] ?? [200, 200, 200];
      out[i * 4] = col[0];
      out[i * 4 + 1] = col[1];
      out[i * 4 + 2] = col[2];
      const inMove = onlyMove == null || c.move[i] === onlyMove;
      const inStage = onlyStage == null || c.stage[i] === onlyStage;
      out[i * 4 + 3] = inMove && inStage ? 1 : 0;
    }
    gl.setState(out);
    drawRef.current();
  }, [c, onlyMove, onlyStage, moveIds]);

  // interaction: zoom at cursor, drag to pan, hover, click
  const drag = useRef<null | { x: number; y: number; v: FloorView; moved: boolean }>(null);
  const toData = (px: number, py: number) => {
    const { w, h } = sizeRef.current;
    const v = aspectView(viewRef.current, w, h);
    return [v.xmin + (px / w) * (v.xmax - v.xmin), v.ymax - (py / h) * (v.ymax - v.ymin)];
  };
  const nearest = (px: number, py: number, r = 10) => {
    if (!c) return -1;
    const { w, h } = sizeRef.current;
    const v = aspectView(viewRef.current, w, h);
    const sx = w / (v.xmax - v.xmin);
    const sy = h / (v.ymax - v.ymin);
    let best = -1;
    let bd = r * r;
    for (let i = 0; i < c.N; i++) {
      if ((onlyMove != null && c.move[i] !== onlyMove) || (onlyStage != null && c.stage[i] !== onlyStage)) continue;
      const x = (c.xy[i * 2] - v.xmin) * sx;
      const y = (v.ymax - c.xy[i * 2 + 1]) * sy;
      const d = (x - px) ** 2 + (y - py) ** 2;
      if (d < bd) {
        bd = d;
        best = i;
      }
    }
    return best;
  };
  const local = (e: React.PointerEvent | React.WheelEvent) => {
    if (!wrap.current) return [0, 0];
    const r = wrap.current.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  };
  const onWheel = (e: React.WheelEvent) => {
    const [px, py] = local(e);
    const [dx, dy] = toData(px, py);
    const f = Math.exp(e.deltaY * 0.0015);
    const v = viewRef.current;
    const nv = { xmin: dx + (v.xmin - dx) * f, xmax: dx + (v.xmax - dx) * f, ymin: dy + (v.ymin - dy) * f, ymax: dy + (v.ymax - dy) * f };
    if (nv.xmax - nv.xmin > 1.6 || nv.xmax - nv.xmin < 0.01) return;
    viewRef.current = nv;
    drawRef.current();
  };
  const onDown = (e: React.PointerEvent) => {
    const [x, y] = local(e);
    drag.current = { x, y, v: { ...viewRef.current }, moved: false };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };
  const onMove = (e: React.PointerEvent) => {
    const [x, y] = local(e);
    const d = drag.current;
    if (d) {
      if (Math.hypot(x - d.x, y - d.y) > 4) d.moved = true;
      if (d.moved) {
        const { w, h } = sizeRef.current;
        const v = aspectView(d.v, w, h);
        const kx = (v.xmax - v.xmin) / w;
        const ky = (v.ymax - v.ymin) / h;
        viewRef.current = { xmin: d.v.xmin - (x - d.x) * kx, xmax: d.v.xmax - (x - d.x) * kx, ymin: d.v.ymin + (y - d.y) * ky, ymax: d.v.ymax + (y - d.y) * ky };
        drawRef.current();
        return;
      }
    }
    if (e.pointerType === "touch") return;
    const i = nearest(x, y);
    hoverRef.current = i;
    setHover(i >= 0 ? { i, x, y } : null);
    drawRef.current();
  };
  const onUp = (e: React.PointerEvent) => {
    const d = drag.current;
    drag.current = null;
    if (!d || d.moved || !c) return;
    const [x, y] = local(e);
    const i = nearest(x, y, e.pointerType === "touch" ? 18 : 10);
    if (i >= 0) window.location.hash = `#/stage/${encodeURIComponent(c.doc.stages[c.stage[i]])}?block=${c.block[i]}`;
  };

  return (
    <div className="constellation">
      <Nav active="constellation" />
      <div className="constellation__sky" ref={wrap} onWheel={onWheel} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={() => { hoverRef.current = -1; setHover(null); drawRef.current(); }} onDoubleClick={() => { viewRef.current = { ...FULL }; drawRef.current(); }}>
        <canvas ref={canvas} className="constellation__gl" />
        {hover && c && (
          <div className="constellation__tip" style={{ left: hover.x + 14, top: hover.y + 14 }}>
            <div className="eyebrow">{stageName(c.stage[hover.i])}</div>
            <strong>
              <i style={{ background: MOVE_COLORS[moveIds[c.move[hover.i]]] }} />
              {MOVE_NAMES[moveIds[c.move[hover.i]]] ?? moveIds[c.move[hover.i]]}
            </strong>
            <span>Hectare #{fmtInt(c.block[hover.i])} · click to see it dance</span>
          </div>
        )}
      </div>
      <div className="constellation__panel">
        <div className="eyebrow">The constellation</div>
        <h1>Every dance NISAR saw</h1>
        <p>
          Every hectare from every stage, placed by the shape of its dance rather than its place on Earth. Hectares that move alike gather together, wherever
          they are. Scroll to zoom, drag to pan, click a star to see it dance.
        </p>
        {c === null && <p className="dim">The constellation has not been computed yet.</p>}
        {c && (
          <>
            <div className="constellation__legend">
              {moveIds.map((m, i) =>
                counts[i] ? (
                  <button key={m} className={`legend__item ${onlyMove === i ? "is-on" : ""}`} onClick={() => setOnlyMove(onlyMove === i ? null : i)}>
                    <span className="swatch" style={{ background: m === "still" ? "#c4c8d6" : MOVE_COLORS[m] }} />
                    {MOVE_NAMES[m] ?? m}
                    <span className="legend__n">{fmtInt(counts[i])}</span>
                  </button>
                ) : null,
              )}
            </div>
            <div className="constellation__stages">
              {c.doc.stages.map((s, si) => (
                <button key={s} className={`chip ${onlyStage === si ? "is-on" : ""}`} onClick={() => setOnlyStage(onlyStage === si ? null : si)}>
                  {stageName(si)}
                </button>
              ))}
            </div>
            <div className="dim" style={{ fontSize: 12, marginTop: 10 }}>
              {fmtInt(c.N)} hectares from {c.doc.stages.length} stages
            </div>
            {c.fixture && (
              <div style={{ marginTop: 12 }}>
                <FixtureTag />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

/** Keep the sky's aspect ratio square in data units. */
function aspectView(v: FloorView, w: number, h: number): FloorView {
  const cx = (v.xmin + v.xmax) / 2;
  const cy = (v.ymin + v.ymax) / 2;
  const span = Math.max(v.xmax - v.xmin, v.ymax - v.ymin);
  const a = w / Math.max(1, h);
  return a >= 1
    ? { xmin: cx - (span * a) / 2, xmax: cx + (span * a) / 2, ymin: cy - span / 2, ymax: cy + span / 2 }
    : { xmin: cx - span / 2, xmax: cx + span / 2, ymin: cy - span / a / 2, ymax: cy + span / a / 2 };
}

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { FloorGL, type FloorView } from "./floorGL";
import type { Clock, Frame } from "./clock";
import type { DecodeResult } from "./decoded";
import type { FloorSpec, FloorZone } from "../lib/types";
import { ZONE_TINTS, hexToRgb } from "../lib/moves";
import { pointInPolygon, positionOf, positionsAt } from "./positions";
import type { Signal } from "../lib/signal";
import { fmtDb } from "../lib/format";

export interface TrailSpec {
  name: string;
  ks: ArrayLike<number>;
  gain: number;
  width: number;
  tau?: number;
  future?: number;
  tint?: [number, number, number] | null;
}

export type BrushTool = "rect" | "lasso" | "none";

interface Props {
  data: DecodeResult;
  floor: FloorSpec;
  hhOnly: boolean;
  clock: Clock;
  state: Uint8Array;
  stateVersion: number;
  selActive: boolean;
  trails: TrailSpec[];
  hover?: Signal<number>;
  solo?: number | null;
  tool?: BrushTool;
  onSelect?: (mask: Uint8Array | null, count: number, final: boolean) => void;
  onPick?: (k: number | null) => void;
  emphasizeZone?: string | null;
  compact?: boolean;
  showZoneLabels?: boolean;
  pointScale?: number;
  exposure?: number;
  ariaLabel?: string;
}

interface Geo {
  x: number;
  y: number;
  w: number;
  h: number;
  s: number;
}

const ZONE_LABEL_POS: Record<string, "above" | "below" | "left" | "right"> = {
  water: "above",
  soil: "below",
  crops: "left",
  forest: "left",
  bounce: "above",
};

export function floorView(floor: FloorSpec, hhOnly: boolean, range?: [number, number] | null): FloorView {
  if (hhOnly) {
    const [lo, hi] = range ?? [floor.x.min, floor.x.max];
    return { xmin: lo, xmax: hi, ymin: lo, ymax: hi };
  }
  return { xmin: floor.x.min, xmax: floor.x.max, ymin: floor.y.min, ymax: floor.y.max };
}

function computeGeo(w: number, h: number, v: FloorView, compact: boolean): Geo {
  const ml = compact ? 30 : 50;
  const mr = compact ? 8 : 14;
  const mt = compact ? 8 : 12;
  const mb = compact ? 28 : 44;
  const dbW = v.xmax - v.xmin;
  const dbH = v.ymax - v.ymin;
  const s = Math.max(0.5, Math.min((w - ml - mr) / dbW, (h - mt - mb) / dbH));
  const pw = dbW * s;
  const ph = dbH * s;
  return { x: ml + Math.max(0, (w - ml - mr - pw) / 2), y: mt + Math.max(0, (h - mt - mb - ph) / 2), w: pw, h: ph, s };
}

export function DanceFloor(props: Props) {
  const { data, floor, hhOnly, clock, state, stateVersion, selActive, trails, hover, solo = null, tool = "rect", onSelect, onPick, emphasizeZone = null, compact = false, showZoneLabels = true, pointScale = 1, exposure = 1.1 } = props;
  const wrapRef = useRef<HTMLDivElement>(null);
  const glCanvas = useRef<HTMLCanvasElement>(null);
  const zoneCanvas = useRef<HTMLCanvasElement>(null);
  const glRef = useRef<FloorGL | null>(null);
  const frameRef = useRef<Frame>(clock.frame());
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [glError, setGlError] = useState<string | null>(null);
  const [drag, setDrag] = useState<null | { kind: "rect" | "lasso"; pts: [number, number][] }>(null);
  const hoverRing = useRef<SVGCircleElement>(null);
  const soloRing = useRef<SVGGElement>(null);
  const view = useMemo(() => floorView(floor, hhOnly, data.range), [floor, hhOnly, data.range]);
  const geo = useMemo(() => computeGeo(size.w, size.h, view, compact), [size, view, compact]);
  const geoRef = useRef(geo);
  geoRef.current = geo;
  const soloRef = useRef(solo);
  soloRef.current = solo;
  const selActiveRef = useRef(selActive);
  selActiveRef.current = selActive;

  // size
  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      setSize({ w: Math.round(r.width), h: Math.round(r.height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // GL init
  useEffect(() => {
    if (!glCanvas.current) return;
    try {
      glRef.current = new FloorGL(glCanvas.current);
    } catch (e) {
      setGlError(String((e as Error).message || e));
    }
    return () => {
      glRef.current?.destroy();
      glRef.current = null;
    };
  }, []);

  const pointPx = useMemo(() => {
    const area = geo.w * geo.h;
    const per = area / Math.max(1, data.K);
    const base = Math.min(3.6, Math.max(2.0, Math.sqrt(per) * 1.25));
    return base * pointScale * (compact ? 0.95 : 1);
  }, [geo, data.K, pointScale, compact]);

  const gain = useMemo(() => {
    const area = geo.w * geo.h;
    const per = area / Math.max(1, data.K);
    return Math.min(0.9, Math.max(0.1, 0.42 * Math.sqrt(per / 3.5)));
  }, [geo, data.K]);

  const draw = useCallback(
    (fr: Frame) => {
      const gl = glRef.current;
      if (!gl) return;
      gl.draw({
        i0: fr.i0,
        i1: fr.i1,
        e: fr.e,
        head: fr.head,
        view,
        selActive: selActiveRef.current,
        pointPx,
        gain,
        exposure,
        dimOthers: 0.14,
        hoverK: hover ? hover.get() : -1,
      });
      // rings
      const g = geoRef.current;
      const place = (k: number, el: SVGElement | null) => {
        if (!el) return;
        if (k == null || k < 0) {
          el.style.display = "none";
          return;
        }
        const [x, y] = positionOf(data, k, fr);
        el.style.display = "";
        el.setAttribute("transform", `translate(${g.x + (x - view.xmin) * g.s},${g.y + (view.ymax - y) * g.s})`);
      };
      place(hover ? hover.get() : -1, hoverRing.current);
      place(soloRef.current ?? -1, soloRing.current);
    },
    [view, pointPx, gain, hover, data, exposure],
  );
  const drawRef = useRef(draw);
  drawRef.current = draw;

  // data upload
  useEffect(() => {
    glRef.current?.setData(data.xy, data.T, data.K);
    clock.invalidate();
  }, [data, clock]);

  useEffect(() => {
    glRef.current?.setState(state);
    drawRef.current(frameRef.current);
  }, [state, stateVersion]);

  useEffect(() => {
    const gl = glRef.current;
    if (!gl) return;
    const names = new Set(trails.map((t) => t.name));
    for (const t of trails) gl.setTrails(t.name, t.ks, { gain: t.gain, width: t.width, tau: t.tau, future: t.future, tint: t.tint });
    for (const n of ["sel", "hl", "solo"]) if (!names.has(n)) gl.setTrails(n, [], { gain: 0, width: 1 });
    drawRef.current(frameRef.current);
  }, [trails]);

  // resize GL
  useEffect(() => {
    const gl = glRef.current;
    if (!gl || geo.w < 2) return;
    gl.resize(geo.w, geo.h, Math.min(window.devicePixelRatio || 1, 2));
    drawRef.current(frameRef.current);
  }, [geo]);

  // frames
  useEffect(() => {
    return clock.subscribe((fr) => {
      frameRef.current = fr;
      drawRef.current(fr);
    });
  }, [clock]);

  useEffect(() => {
    drawRef.current(frameRef.current);
  }, [solo, selActive, draw]);

  useEffect(() => {
    if (!hover) return;
    return hover.subscribe(() => drawRef.current(frameRef.current));
  }, [hover]);

  // zones background
  useEffect(() => {
    const c = zoneCanvas.current;
    if (!c || geo.w < 2) return;
    drawZones(c, geo, view, hhOnly ? [] : floor.zones, emphasizeZone);
  }, [geo, view, floor, hhOnly, emphasizeZone]);

  // ---- interaction
  const toDb = (px: number, py: number): [number, number] => {
    const g = geoRef.current;
    return [view.xmin + (px - g.x) / g.s, view.ymax - (py - g.y) / g.s];
  };
  const local = (e: React.PointerEvent) => {
    const r = wrapRef.current!.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top] as [number, number];
  };
  const pickAt = (px: number, py: number, radius: number) => {
    const g = geoRef.current;
    const pos = positionsAt(data, frameRef.current);
    let best = -1;
    let bd = radius * radius;
    for (let k = 0; k < data.K; k++) {
      const x = g.x + (pos[k * 2] - view.xmin) * g.s;
      const y = g.y + (view.ymax - pos[k * 2 + 1]) * g.s;
      const d = (x - px) ** 2 + (y - py) ** 2;
      if (d < bd) {
        bd = d;
        best = k;
      }
    }
    return best;
  };
  const selectWith = (kind: "rect" | "lasso", pts: [number, number][], final: boolean) => {
    if (!onSelect) return;
    const pos = positionsAt(data, frameRef.current);
    const mask = new Uint8Array(data.K);
    let count = 0;
    if (kind === "rect") {
      const [a, b] = [toDb(pts[0][0], pts[0][1]), toDb(pts[pts.length - 1][0], pts[pts.length - 1][1])];
      const x0 = Math.min(a[0], b[0]);
      const x1 = Math.max(a[0], b[0]);
      const y0 = Math.min(a[1], b[1]);
      const y1 = Math.max(a[1], b[1]);
      for (let k = 0; k < data.K; k++) {
        const x = pos[k * 2];
        const y = pos[k * 2 + 1];
        if (x >= x0 && x <= x1 && y >= y0 && y <= y1) {
          mask[k] = 1;
          count++;
        }
      }
    } else {
      const poly = pts.map((p) => toDb(p[0], p[1]));
      let x0 = Infinity;
      let x1 = -Infinity;
      let y0 = Infinity;
      let y1 = -Infinity;
      for (const [x, y] of poly) {
        x0 = Math.min(x0, x);
        x1 = Math.max(x1, x);
        y0 = Math.min(y0, y);
        y1 = Math.max(y1, y);
      }
      for (let k = 0; k < data.K; k++) {
        const x = pos[k * 2];
        const y = pos[k * 2 + 1];
        if (x < x0 || x > x1 || y < y0 || y > y1) continue;
        if (pointInPolygon(x, y, poly)) {
          mask[k] = 1;
          count++;
        }
      }
    }
    onSelect(count ? mask : null, count, final);
  };

  const dragRef = useRef<null | { kind: "rect" | "lasso"; pts: [number, number][]; moved: boolean; id: number }>(null);
  const hoverRaf = useRef(0);
  const selRaf = useRef(0);
  const interactive = !!(onSelect || onPick);

  const onPointerDown = (e: React.PointerEvent) => {
    if (!interactive || e.button > 0) return;
    const p = local(e);
    const kind: "rect" | "lasso" = tool === "lasso" ? "lasso" : "rect";
    dragRef.current = { kind, pts: [p], moved: false, id: e.pointerId };
    if (tool !== "none") (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const p = local(e);
    const d = dragRef.current;
    if (d && tool !== "none") {
      const p0 = d.pts[0];
      if (!d.moved && Math.hypot(p[0] - p0[0], p[1] - p0[1]) > 5) d.moved = true;
      if (!d.moved) return;
      if (d.kind === "rect") d.pts = [p0, p];
      else d.pts.push(p);
      setDrag({ kind: d.kind, pts: d.pts.slice() });
      if (!selRaf.current)
        selRaf.current = requestAnimationFrame(() => {
          selRaf.current = 0;
          const dd = dragRef.current;
          if (dd && dd.moved && (dd.kind === "rect" || dd.pts.length > 2)) selectWith(dd.kind, dd.pts, false);
        });
      return;
    }
    if (!hover || e.pointerType === "touch") return;
    if (hoverRaf.current) return;
    hoverRaf.current = requestAnimationFrame(() => {
      hoverRaf.current = 0;
      hover.set(pickAt(p[0], p[1], 9));
    });
  };
  const onPointerUp = (e: React.PointerEvent) => {
    const d = dragRef.current;
    dragRef.current = null;
    setDrag(null);
    if (!d) return;
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(d.id);
    } catch {
      /* not captured */
    }
    if (!d.moved) {
      const p = local(e);
      const k = pickAt(p[0], p[1], e.pointerType === "touch" ? 18 : 11);
      onPick?.(k >= 0 ? k : null);
      if (k < 0) onSelect?.(null, 0, true);
      return;
    }
    if (d.kind === "rect" || d.pts.length > 2) selectWith(d.kind, d.pts, true);
  };
  const onPointerLeave = () => {
    if (!dragRef.current) hover?.set(-1);
  };

  // ---- axes
  const ticksX: number[] = [];
  const ticksY: number[] = [];
  for (let v = Math.ceil(view.xmin / 5) * 5; v <= view.xmax; v += 5) ticksX.push(v);
  for (let v = Math.ceil(view.ymin / 5) * 5; v <= view.ymax; v += 5) ticksY.push(v);
  const X = (v: number) => geo.x + (v - view.xmin) * geo.s;
  const Y = (v: number) => geo.y + (view.ymax - v) * geo.s;

  return (
    <div
      ref={wrapRef}
      className={`floor ${compact ? "floor--compact" : ""} ${tool === "none" ? "floor--notool" : ""}`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onPointerLeave={onPointerLeave}
      role="img"
      aria-label={props.ariaLabel || "Dance floor: every hectare as a dot, HH across and HV up"}
    >
      <canvas ref={zoneCanvas} className="floor__zones" style={{ left: geo.x, top: geo.y, width: geo.w, height: geo.h }} />
      <svg className="floor__axes" width={size.w} height={size.h}>
        <rect x={geo.x} y={geo.y} width={geo.w} height={geo.h} className="floor__frame" />
        {ticksX.map((v) => (
          <g key={`x${v}`}>
            <line x1={X(v)} x2={X(v)} y1={geo.y} y2={geo.y + geo.h} className="floor__grid" />
            <text x={X(v)} y={geo.y + geo.h + (compact ? 13 : 16)} className="floor__tick" textAnchor="middle">
              {fmtDb(v, 0)}
            </text>
          </g>
        ))}
        {ticksY.map((v) => (
          <g key={`y${v}`}>
            <line x1={geo.x} x2={geo.x + geo.w} y1={Y(v)} y2={Y(v)} className="floor__grid" />
            <text x={geo.x - 7} y={Y(v) + 3.5} className="floor__tick" textAnchor="end">
              {fmtDb(v, 0)}
            </text>
          </g>
        ))}
        {hhOnly && (
          <g>
            <line x1={X(view.xmin)} y1={Y(view.ymin)} x2={X(view.xmax)} y2={Y(view.ymax)} className="floor__zero" />
            <text transform={`translate(${X(view.xmin + (view.xmax - view.xmin) * 0.3)},${Y(view.ymin + (view.ymax - view.ymin) * 0.3) - 8}) rotate(-45)`} className="floor__diag" textAnchor="middle">
              no change since the first pass
            </text>
            {!compact && (
              <>
                <text x={X(view.xmin) + 14} y={Y(view.ymax) + 24} className="floor__zone-main floor__hh-label">louder than at the start</text>
                <text x={X(view.xmax) - 14} y={Y(view.ymin) - 16} className="floor__zone-main floor__hh-label" textAnchor="end">quieter than at the start</text>
              </>
            )}
          </g>
        )}
        {!compact && (
          <>
            <text x={geo.x + geo.w} y={geo.y + geo.h + 36} className="floor__axis-title" textAnchor="end">
              {hhOnly ? (
                <><tspan className="floor__pol floor__pol--hh">HH</tspan> on the first pass, dB →</>
              ) : (
                <><tspan className="floor__pol floor__pol--hh">HH</tspan> hears surfaces and bounces, dB →</>
              )}
            </text>
            <text transform={`translate(${geo.x - 38},${geo.y}) rotate(-90)`} className="floor__axis-title" textAnchor="end">
              {hhOnly ? (
                <><tspan className="floor__pol floor__pol--hh">HH</tspan> on this pass, dB →</>
              ) : (
                <><tspan className="floor__pol floor__pol--hv">HV</tspan> hears leaves and branches, dB →</>
              )}
            </text>
          </>
        )}
        {compact && (
          <>
            <text x={geo.x + geo.w} y={geo.y + geo.h + 26} className="floor__axis-title floor__axis-title--sm" textAnchor="end">
              HH →
            </text>
            <text transform={`translate(${geo.x - 22},${geo.y}) rotate(-90)`} className="floor__axis-title floor__axis-title--sm" textAnchor="end">
              {hhOnly ? "HH now →" : "HV →"}
            </text>
          </>
        )}
      </svg>
      <canvas ref={glCanvas} className="floor__gl" style={{ left: geo.x, top: geo.y, width: geo.w, height: geo.h }} />
      <svg className="floor__over" width={size.w} height={size.h}>
        {showZoneLabels && !hhOnly && geo.w > 10 &&
          floor.zones.map((z) => <ZoneLabel key={z.id} z={z} X={X} Y={Y} compact={compact} emph={emphasizeZone} xmax={view.xmax} />)}
        <circle ref={hoverRing} r={7} className="floor__hover" style={{ display: "none" }} />
        <g ref={soloRing} style={{ display: "none" }}>
          <circle r={9} className="floor__solo" />
          <circle r={15} className="floor__solo floor__solo--outer" />
        </g>
        {drag && drag.kind === "rect" && drag.pts.length === 2 && (
          <rect
            x={Math.min(drag.pts[0][0], drag.pts[1][0])}
            y={Math.min(drag.pts[0][1], drag.pts[1][1])}
            width={Math.abs(drag.pts[1][0] - drag.pts[0][0])}
            height={Math.abs(drag.pts[1][1] - drag.pts[0][1])}
            className="floor__brush"
          />
        )}
        {drag && drag.kind === "lasso" && <path d={`M${drag.pts.map((p) => p.join(",")).join("L")}Z`} className="floor__brush" />}
      </svg>
      {glError && <div className="floor__error">This browser cannot draw the dance floor (WebGL2 unavailable).</div>}
    </div>
  );
}

function ZoneLabel({ z, X, Y, compact, emph, xmax }: { z: FloorZone; X: (v: number) => number; Y: (v: number) => number; compact: boolean; emph: string | null; xmax: number }) {
  const [main, sub] = z.label.split(":").map((s) => s.trim());
  const pos = ZONE_LABEL_POS[z.id] || "above";
  const off = compact ? 2.4 : 3.1;
  let x = z.center[0];
  let y = z.center[1];
  let anchor: "middle" | "end" | "start" = "middle";
  if (pos === "above") y += off + 0.6;
  if (pos === "below") y -= off + 0.8;
  if (pos === "left") {
    x -= off + 0.4;
    anchor = "end";
  }
  if (pos === "right") {
    x += off;
    anchor = "start";
  }
  // labels near the right edge hang from the edge instead of running off the floor
  if (anchor === "middle" && z.center[0] > xmax - 9) {
    x = xmax - 0.5;
    anchor = "end";
  }
  const dim = emph && emph !== z.id;
  return (
    <g className={`floor__zone-label ${dim ? "is-dim" : ""} ${emph === z.id ? "is-emph" : ""}`} transform={`translate(${X(x)},${Y(y)})`}>
      <text textAnchor={anchor} className="floor__zone-main">
        {main}
      </text>
      {sub && !compact && (
        <text textAnchor={anchor} y={14} className="floor__zone-sub">
          {sub}
        </text>
      )}
    </g>
  );
}

function drawZones(c: HTMLCanvasElement, g: Geo, v: FloorView, zones: FloorZone[], emph: string | null) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const scale = 0.5;
  const W = Math.max(2, Math.round(g.w * dpr * scale));
  const H = Math.max(2, Math.round(g.h * dpr * scale));
  c.width = W;
  c.height = H;
  const ctx = c.getContext("2d");
  if (!ctx) return;
  ctx.clearRect(0, 0, W, H);
  if (!zones.length) return;
  const img = ctx.createImageData(W, H);
  const cols = zones.map((z) => hexToRgb(ZONE_TINTS[z.id] || "#555555"));
  const dx = (v.xmax - v.xmin) / W;
  const dy = (v.ymax - v.ymin) / H;
  const edgeW = 0.18 * (dx * 2 + 0.2);
  for (let py = 0; py < H; py++) {
    const yv = v.ymax - (py + 0.5) * dy;
    for (let px = 0; px < W; px++) {
      const xv = v.xmin + (px + 0.5) * dx;
      let d1 = Infinity;
      let d2 = Infinity;
      let i1 = 0;
      for (let i = 0; i < zones.length; i++) {
        const ex = xv - zones[i].center[0];
        const ey = yv - zones[i].center[1];
        const d = Math.sqrt(ex * ex + ey * ey);
        if (d < d1) {
          d2 = d1;
          d1 = d;
          i1 = i;
        } else if (d < d2) d2 = d;
      }
      let a = 0.035 + 0.11 * Math.exp(-(d1 * d1) / 22);
      const edge = (d2 - d1) / 2;
      if (edge < edgeW * 2.5) a += 0.035 * Math.max(0, 1 - edge / (edgeW * 2.5));
      if (emph) a *= zones[i1].id === emph ? 2.6 : 0.4;
      const o = (py * W + px) * 4;
      const col = cols[i1];
      img.data[o] = col[0];
      img.data[o + 1] = col[1];
      img.data[o + 2] = col[2];
      img.data[o + 3] = Math.min(255, a * 255);
    }
  }
  ctx.putImageData(img, 0, 0);
}

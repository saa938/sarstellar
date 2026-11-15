import { useEffect, useMemo, useRef } from "react";
import type { FloorSpec, PathPoint } from "../lib/types";
import { MOVE_COLORS, ZONE_TINTS } from "../lib/moves";
import { ease, prefersReducedMotion } from "../stage/clock";

// one shared ticker for every mini floor on the page
type Fn = (t: number) => void;
const subs = new Set<Fn>();
let raf = 0;
const loop = (now: number) => {
  for (const f of subs) f(now / 1000);
  raf = subs.size ? requestAnimationFrame(loop) : 0;
};
function subscribe(fn: Fn) {
  subs.add(fn);
  if (!raf) raf = requestAnimationFrame(loop);
  return () => {
    subs.delete(fn);
  };
}

interface Props {
  moveId: string;
  path: PathPoint[];
  floor: FloorSpec;
  beat?: number; // seconds per step
  size?: "sm" | "md" | "lg";
  showZones?: boolean;
  showLabels?: boolean;
}

/** The canonical path of a move, danced by one glowing dot on a tiny floor. */
export function MiniFloor({ moveId, path, floor, beat = 0.9, size = "md", showZones = true, showLabels = false }: Props) {
  const W = 200;
  const H = 170;
  const pad = { l: 8, r: 8, t: 8, b: 8 };
  const hhOnly = path.every((p) => p.HV == null);
  const x0 = floor.x.min;
  const x1 = floor.x.max;
  const y0 = floor.y.min;
  const y1 = floor.y.max;
  const X = (v: number) => pad.l + ((v - x0) / (x1 - x0)) * (W - pad.l - pad.r);
  const Y = (v: number | null) => (v == null ? H / 2 : pad.t + ((y1 - v) / (y1 - y0)) * (H - pad.t - pad.b));
  const pts = useMemo(() => path.map((p) => [X(p.HH), Y(p.HV)] as [number, number]), [path]); // eslint-disable-line react-hooks/exhaustive-deps
  const dot = useRef<SVGGElement>(null);
  const trail = useRef<SVGPathElement>(null);
  const wrap = useRef<SVGSVGElement>(null);
  const color = MOVE_COLORS[moveId] ?? "#ddd";
  const id = `mf-${moveId}-${size}`;

  useEffect(() => {
    if (pts.length < 2) return;
    const reduced = prefersReducedMotion();
    let visible = true;
    const io = new IntersectionObserver(([e]) => (visible = e.isIntersecting), { rootMargin: "100px" });
    if (wrap.current) io.observe(wrap.current);
    const n = pts.length;
    const holdSteps = 1.2;
    const cycle = n - 1 + holdSteps;
    const place = (t: number) => {
      if (!visible || !dot.current) return;
      const tau = reduced ? n - 1 : (t / beat) % cycle;
      const i = Math.min(Math.floor(tau), n - 2);
      const f = tau >= n - 1 ? 1 : ease(Math.min(1, tau - i));
      const p = [pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f];
      dot.current.setAttribute("transform", `translate(${p[0].toFixed(2)},${p[1].toFixed(2)})`);
      if (trail.current) {
        let d = `M${pts[0][0]},${pts[0][1]}`;
        for (let j = 1; j <= i; j++) d += `L${pts[j][0]},${pts[j][1]}`;
        d += `L${p[0].toFixed(2)},${p[1].toFixed(2)}`;
        trail.current.setAttribute("d", d);
      }
    };
    place(0);
    const unsub = subscribe(place);
    return () => {
      unsub();
      io.disconnect();
    };
  }, [pts, beat]);

  const full = `M${pts.map((p) => p.join(",")).join("L")}`;
  return (
    <svg ref={wrap} className={`minifloor minifloor--${size}`} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`The ${moveId} path on the dance floor`}>
      <defs>
        {floor.zones.map((z) => (
          <radialGradient key={z.id} id={`${id}-z-${z.id}`}>
            <stop offset="0" stopColor={ZONE_TINTS[z.id] ?? "#555"} stopOpacity="0.5" />
            <stop offset="1" stopColor={ZONE_TINTS[z.id] ?? "#555"} stopOpacity="0" />
          </radialGradient>
        ))}
        <filter id={`${id}-glow`} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="3" />
        </filter>
      </defs>
      <rect x="0.5" y="0.5" width={W - 1} height={H - 1} rx="10" className="minifloor__bg" />
      {showZones && !hhOnly &&
        floor.zones.map((z) => <ellipse key={z.id} cx={X(z.center[0])} cy={Y(z.center[1])} rx={34} ry={30} fill={`url(#${id}-z-${z.id})`} />)}
      {showLabels && !hhOnly &&
        floor.zones.map((z) => (
          <text key={z.id} x={X(z.center[0])} y={Y(z.center[1]) + 3} className="minifloor__zone" textAnchor="middle">
            {z.label.split(":")[0]}
          </text>
        ))}
      {hhOnly && (
        <>
          <line x1={pad.l + 6} x2={W - pad.r - 6} y1={H / 2} y2={H / 2} className="minifloor__track" />
          <text x={W / 2} y={H / 2 + 26} className="minifloor__zone" textAnchor="middle">
            HH only, louder to the right
          </text>
        </>
      )}
      <path d={full} className="minifloor__path" />
      <path ref={trail} className="minifloor__trail" style={{ stroke: color }} />
      <g ref={dot}>
        <circle r="9" fill={color} opacity="0.55" filter={`url(#${id}-glow)`} />
        <circle r="3.6" fill="#fff" />
        <circle r="5.5" fill="none" stroke={color} strokeWidth="1.4" />
      </g>
    </svg>
  );
}

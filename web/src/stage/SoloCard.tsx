import { useEffect, useMemo, useRef, useState } from "react";
import type { DecodeResult } from "./decoded";
import type { Clock } from "./clock";
import type { FloorZone, MoveDef } from "../lib/types";
import { MOVE_COLORS, POL_COLORS } from "../lib/moves";
import { fmtDate, fmtDb, fmtInt, parseDate } from "../lib/format";
import { formatLonLat } from "../lib/geo";
import { readBlock } from "./explain";

interface Props {
  data: DecodeResult;
  k: number;
  dates: string[];
  nx: number;
  clock: Clock;
  zones: FloorZone[];
  hhOnly: boolean;
  moveIds: string[] | null;
  moves: MoveDef[];
  fixture: boolean;
  onClose: () => void;
}

export function SoloCard({ data, k, dates, nx, clock, zones, hhOnly, moveIds, moves, fixture, onClose }: Props) {
  const n = data.idx[k];
  const row = Math.floor(n / nx);
  const col = n % nx;
  const lon = data.lonlat[k * 2];
  const lat = data.lonlat[k * 2 + 1];
  const moveIdx = data.move ? data.move[k] : 255;
  const moveId = moveIds && moveIdx < moveIds.length ? moveIds[moveIdx] : null;
  const moveDef = moveId ? moves.find((m) => m.id === moveId) ?? null : null;
  const conf = data.conf ? data.conf[k] : null;
  const reading = useMemo(() => readBlock(data, k, dates, zones, hhOnly, moveDef), [data, k, dates, zones, hhOnly, moveDef]);

  return (
    <div className="solo" role="dialog" aria-label="One hectare">
      <div className="solo__head">
        <div>
          <div className="eyebrow">One hectare · #{fmtInt(n)}</div>
          <div className="solo__where">
            {formatLonLat(lon, lat)} <span className="dim">· row {row}, col {col}</span>
          </div>
        </div>
        <button className="btn-icon" onClick={onClose} aria-label="Close">
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden>
            <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </button>
      </div>
      {moveId && (
        <div className="solo__move">
          <span className="swatch" style={{ background: MOVE_COLORS[moveId] }} />
          <strong>{moveDef?.name ?? moveId}</strong>
          {conf != null && <span className="dim">{conf}% confidence</span>}
        </div>
      )}
      {!moveId && <div className="solo__move solo__move--plain">{reading.headline}</div>}
      <SoloChart data={data} k={k} dates={dates} clock={clock} hhOnly={hhOnly} />
      <p className="solo__text">{reading.sentences.join(" ")}</p>
      <div className="solo__foot">
        {reading.kind === "textbook" ? "A textbook reading of this hectare's numbers, not a model output." : fixture ? "Move from synthetic preview data." : "Move from the SARstellar model."}
      </div>
    </div>
  );
}

function SoloChart({ data, k, dates, clock, hhOnly }: { data: DecodeResult; k: number; dates: string[]; clock: Clock; hhOnly: boolean }) {
  const W = 340;
  const H = 132;
  const m = { l: 30, r: 30, t: 10, b: 20 };
  const T = data.T;
  const K = data.K;
  const cursor = useRef<SVGGElement>(null);
  const [hoverT, setHoverT] = useState<number | null>(null);
  const series = useMemo(() => {
    const hh: (number | null)[] = [];
    const hv: (number | null)[] = [];
    for (let t = 0; t < T; t++) {
      const ok = data.valid[t * K + k];
      const x = data.xy[(t * K + k) * 2 + (hhOnly ? 1 : 0)];
      hh.push(ok ? x : null);
      // HH-only: show the raw HH series alone
      hv.push(ok && !hhOnly ? data.xy[(t * K + k) * 2 + 1] : null);
    }
    return { hh, hv };
  }, [data, k, T, K, hhOnly]);
  const t0 = parseDate(dates[0]);
  const t1 = parseDate(dates[T - 1]);
  const xs = dates.map((d) => m.l + ((parseDate(d) - t0) / Math.max(1, t1 - t0)) * (W - m.l - m.r));
  const vals = [...series.hh, ...series.hv].filter((v): v is number => v != null);
  let lo = Math.min(...vals);
  let hi = Math.max(...vals);
  if (!isFinite(lo)) {
    lo = -30;
    hi = 0;
  }
  const span = Math.max(6, hi - lo);
  const mid = (hi + lo) / 2;
  lo = Math.floor((mid - span / 2 - 1) / 2) * 2;
  hi = Math.ceil((mid + span / 2 + 1) / 2) * 2;
  const y = (v: number) => m.t + ((hi - v) / (hi - lo)) * (H - m.t - m.b);
  const path = (s: (number | null)[]) => {
    let d = "";
    let pen = false;
    s.forEach((v, i) => {
      if (v == null) {
        pen = false;
        return;
      }
      d += `${pen ? "L" : "M"}${xs[i].toFixed(1)},${y(v).toFixed(1)}`;
      pen = true;
    });
    return d;
  };
  const ticks: number[] = [];
  const stepY = hi - lo > 16 ? 5 : hi - lo > 8 ? 4 : 2;
  for (let v = Math.ceil(lo / stepY) * stepY; v <= hi; v += stepY) ticks.push(v);

  useEffect(
    () =>
      clock.subscribe((fr) => {
        if (!cursor.current) return;
        const x = xs[fr.i0] + (xs[fr.i1] - xs[fr.i0]) * fr.e;
        cursor.current.setAttribute("transform", `translate(${x},0)`);
      }),
    // xs is derived from dates which are stable per stage
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [clock, dates],
  );

  const lastIdx = (s: (number | null)[]) => {
    for (let i = s.length - 1; i >= 0; i--) if (s[i] != null) return i;
    return -1;
  };
  const lh = lastIdx(series.hh);
  const lv = lastIdx(series.hv);
  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    let best = 0;
    let bd = Infinity;
    xs.forEach((x, i) => {
      const d = Math.abs(x - px);
      if (d < bd) {
        bd = d;
        best = i;
      }
    });
    setHoverT(best);
  };
  return (
    <div className="solo__chart">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" onPointerMove={onMove} onPointerLeave={() => setHoverT(null)} role="img" aria-label="HH and HV of this hectare over time">
        {ticks.map((v) => (
          <g key={v}>
            <line x1={m.l} x2={W - m.r} y1={y(v)} y2={y(v)} className="chart__grid" />
            <text x={m.l - 6} y={y(v) + 3} textAnchor="end" className="chart__tick">
              {fmtDb(v, 0)}
            </text>
          </g>
        ))}
        <text x={m.l} y={H - 5} className="chart__tick">
          {fmtDate(dates[0], { year: false })}
        </text>
        <text x={W - m.r} y={H - 5} className="chart__tick" textAnchor="end">
          {fmtDate(dates[T - 1])}
        </text>
        <g ref={cursor}>
          <line x1={0} x2={0} y1={m.t - 4} y2={H - m.b} className="chart__cursor" />
        </g>
        <path d={path(series.hv)} className="chart__line" style={{ stroke: POL_COLORS.HV }} />
        <path d={path(series.hh)} className="chart__line" style={{ stroke: POL_COLORS.HH }} />
        {series.hh.map((v, i) => (v == null ? null : <circle key={`h${i}`} cx={xs[i]} cy={y(v)} r={hoverT === i ? 3.6 : 1.8} fill={POL_COLORS.HH} />))}
        {series.hv.map((v, i) => (v == null ? null : <circle key={`v${i}`} cx={xs[i]} cy={y(v)} r={hoverT === i ? 3.6 : 1.8} fill={POL_COLORS.HV} />))}
        {lh >= 0 && (
          <text x={xs[lh] + 6} y={y(series.hh[lh]!) + 3.5} className="chart__label" style={{ fill: POL_COLORS.HH }}>
            HH
          </text>
        )}
        {lv >= 0 && (
          <text x={xs[lv] + 6} y={y(series.hv[lv]!) + 3.5} className="chart__label" style={{ fill: POL_COLORS.HV }}>
            HV
          </text>
        )}
        {hoverT != null && (
          <g>
            <line x1={xs[hoverT]} x2={xs[hoverT]} y1={m.t} y2={H - m.b} className="chart__hover" />
          </g>
        )}
      </svg>
      <div className="solo__readout">
        {hoverT != null ? (
          <>
            <span>{fmtDate(dates[hoverT])}</span>
            <span style={{ color: POL_COLORS.HH }}>HH {series.hh[hoverT] != null ? `${fmtDb(series.hh[hoverT]!)} dB` : "no data"}</span>
            {!hhOnly && <span style={{ color: POL_COLORS.HV }}>HV {series.hv[hoverT] != null ? `${fmtDb(series.hv[hoverT]!)} dB` : "no data"}</span>}
          </>
        ) : (
          <span className="dim">Hover the chart to read each pass. Gaps are passes without data.</span>
        )}
      </div>
    </div>
  );
}

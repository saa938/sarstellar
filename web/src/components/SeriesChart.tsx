// Per-pass backscatter averaged over one change area: NISAR HH/HV in amber, Sentinel-1 VV/VH in cyan,
// with the permanent NISAR data gap shaded (Task B3).
import { CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, Tooltip, XAxis, YAxis } from "recharts";
import { useLayoutEffect, useRef, useState } from "react";
import { AGREEMENT_COLORS, type IsoDate, type Series } from "../types.ts";
import { DAY_MS, formatLevel, gapWithin, longDate, minus, shortDate, thinLabels, toTime } from "./changeFormat.ts";
import "./SeriesChart.css";

export interface SeriesChartProps {
  series: Series;
  /** First date after the change (`area.change_date`); drawn as a dashed line. */
  changeDate?: IsoDate | null;
  width?: number;
  height?: number;
}

type Band = "HH" | "HV" | "VV" | "VH";
type Row = { t: number } & Record<Band, number | null>;

const BANDS: { key: Band; name: string; color: string; dash?: string }[] = [
  { key: "HV", name: "NISAR HV", color: AGREEMENT_COLORS.L },
  { key: "HH", name: "NISAR HH", color: AGREEMENT_COLORS.L, dash: "4 3" },
  { key: "VH", name: "Sentinel-1 VH", color: AGREEMENT_COLORS.C },
  { key: "VV", name: "Sentinel-1 VV", color: AGREEMENT_COLORS.C, dash: "4 3" },
];
const GAP_FILL = "var(--gap)";
const CHANGE_STROKE = "var(--accent)";
const AXIS = { stroke: "var(--muted)", fontSize: 10 };

export default function SeriesChart({ series, changeDate = null, width, height = 170 }: SeriesChartProps) {
  const figure = useRef<HTMLElement>(null);
  const [measuredWidth, setMeasuredWidth] = useState(340);
  const rows = toRows(series);
  const bands = BANDS.filter((b) => rows.some((r) => r[b.key] !== null));
  useLayoutEffect(() => {
    const element = figure.current;
    if (!element || width !== undefined) return;
    const measure = () => {
      const available = Math.floor(element.getBoundingClientRect().width);
      if (available > 0) setMeasuredWidth(available);
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [width, rows.length, bands.length]);
  if (rows.length === 0 || bands.length === 0) {
    return <p className="sc-empty">No pass-by-pass values for this area.</p>;
  }

  let t0 = rows[0].t;
  let t1 = rows[rows.length - 1].t;
  if (t1 - t0 < DAY_MS) {
    t0 -= 3 * DAY_MS;
    t1 += 3 * DAY_MS;
  }
  const gap = gapWithin(t0, t1);
  const change = changeDate ? toTime(changeDate) : NaN;
  const showChange = Number.isFinite(change) && change >= t0 && change <= t1;
  const keep = thinLabels(rows.map((r) => (r.t - t0) / (t1 - t0)), 0.22);
  const ticks = rows.filter((_, i) => keep.has(i)).map((r) => r.t);

  return (
    <figure ref={figure} className="sc" aria-label="Radar brightness at every pass, averaged over this area">
      <LineChart width={width ?? measuredWidth} height={height} data={rows} margin={{ top: 8, right: 10, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--line)" vertical={false} />
        <XAxis
          dataKey="t"
          type="number"
          domain={[t0, t1]}
          ticks={ticks}
          tickFormatter={(t: number) => shortDate(t)}
          {...AXIS}
        />
        <YAxis
          width={50}
          domain={([lo, hi]: readonly number[]) => [Math.floor(lo) - 1, Math.ceil(hi) + 1]}
          allowDecimals={false}
          tickFormatter={(v: number) => `${minus(String(v))} dB`}
          {...AXIS}
        />
        {gap && <ReferenceArea className="sc-gap" x1={gap[0]} x2={gap[1]} fill={GAP_FILL} fillOpacity={0.9} />}
        {showChange && <ReferenceLine x={change} stroke={CHANGE_STROKE} strokeDasharray="2 2" />}
        {bands.map((b) => (
          <Line
            key={b.key}
            dataKey={b.key}
            name={b.name}
            stroke={b.color}
            strokeWidth={2}
            strokeDasharray={b.dash}
            dot={{ r: 2.5, fill: b.color, strokeWidth: 0 }}
            connectNulls
            isAnimationActive={false}
          />
        ))}
        <Tooltip
          contentStyle={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 3, fontSize: 12 }}
          labelStyle={{ color: "var(--text)" }}
          labelFormatter={(t) => longDate(Number(t))}
          formatter={(v) => (typeof v === "number" ? `${formatLevel(v)} dB` : String(v))}
        />
      </LineChart>
      <figcaption className="sc-legend">
        {bands.map((b) => (
          <span key={b.key} className="sc-key" style={{ color: b.color }}>
            <svg width="18" height="6" aria-hidden="true">
              <line x1="0" x2="18" y1="3" y2="3" stroke={b.color} strokeWidth="2" strokeDasharray={b.dash} />
            </svg>
            {b.name}
          </span>
        ))}
        {gap && (
          <span className="sc-key">
            <i className="sc-gap-swatch" aria-hidden="true" />
            No NISAR data
          </span>
        )}
        {showChange && (
          <span className="sc-key" style={{ color: CHANGE_STROKE }}>
            <svg width="18" height="6" aria-hidden="true">
              <line x1="0" x2="18" y1="3" y2="3" stroke={CHANGE_STROKE} strokeWidth="2" strokeDasharray="2 2" />
            </svg>
            Change seen
          </span>
        )}
      </figcaption>
    </figure>
  );
}

function toRows(s: Series): Row[] {
  const val = (arr: (number | null)[] | undefined, i: number) => {
    const v = arr?.[i];
    return typeof v === "number" && Number.isFinite(v) ? v : null;
  };
  return s.dates
    .map((d, i) => ({ t: toTime(d), HH: val(s.HH, i), HV: val(s.HV, i), VV: val(s.VV, i), VH: val(s.VH, i) }))
    .filter((r) => Number.isFinite(r.t))
    .sort((a, b) => a.t - b.t);
}

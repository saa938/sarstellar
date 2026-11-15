import { fmtDate, fmtDb, parseDate } from "../lib/format";

/** One partner only (ice): HH over the season as a simple line. */
export function HHLine({ series, ariaLabel }: { series: { date: string; HH: number }[]; ariaLabel: string }) {
  const W = 620;
  const H = 380;
  const m = { l: 46, r: 24, t: 24, b: 40 };
  if (series.length < 2) return null;
  const t0 = parseDate(series[0].date);
  const t1 = parseDate(series[series.length - 1].date);
  const X = (d: string) => m.l + ((parseDate(d) - t0) / Math.max(1, t1 - t0)) * (W - m.l - m.r);
  const vals = series.map((s) => s.HH);
  const lo = Math.floor(Math.min(...vals) - 1.5);
  const hi = Math.ceil(Math.max(...vals) + 1.5);
  const Y = (v: number) => m.t + ((hi - v) / Math.max(1, hi - lo)) * (H - m.t - m.b);
  const d = series.map((s, i) => `${i ? "L" : "M"}${X(s.date).toFixed(1)},${Y(s.HH).toFixed(1)}`).join("");
  const area = `${d}L${X(series[series.length - 1].date).toFixed(1)},${H - m.b}L${X(series[0].date).toFixed(1)},${H - m.b}Z`;
  const step = hi - lo > 10 ? 4 : 2;
  const ticks: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) ticks.push(v);
  const iMax = vals.indexOf(Math.max(...vals));
  const iMin = vals.indexOf(Math.min(...vals));
  return (
    <figure className="hhline">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={ariaLabel}>
        <defs>
          <linearGradient id="hharea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#7fd6ea" stopOpacity="0.28" />
            <stop offset="1" stopColor="#7fd6ea" stopOpacity="0" />
          </linearGradient>
        </defs>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} className="chart__grid" />
            <text x={m.l - 8} y={Y(v) + 3.5} textAnchor="end" className="chart__tick">
              {fmtDb(v, 0)}
            </text>
          </g>
        ))}
        <path d={area} fill="url(#hharea)" />
        <path d={d} fill="none" stroke="#9fe3f2" strokeWidth={2.4} strokeLinejoin="round" strokeLinecap="round" />
        {series.map((s) => (
          <circle key={s.date} cx={X(s.date)} cy={Y(s.HH)} r={3.2} fill="#e8fbff" />
        ))}
        {[iMin, iMax].map((i) => (
          <text key={i} x={X(series[i].date)} y={Y(series[i].HH) + (i === iMax ? -12 : 20)} textAnchor="middle" className="hhline__label">
            {fmtDate(series[i].date, { year: false })} · {fmtDb(series[i].HH)} dB
          </text>
        ))}
        <text x={m.l} y={H - 10} className="chart__tick">
          {fmtDate(series[0].date)}
        </text>
        <text x={W - m.r} y={H - 10} className="chart__tick" textAnchor="end">
          {fmtDate(series[series.length - 1].date)}
        </text>
        <text x={m.l} y={14} className="hhline__axis">
          HH: surface echo (dB), median of the ice
        </text>
      </svg>
    </figure>
  );
}

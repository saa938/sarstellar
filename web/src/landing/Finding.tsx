import { useEffect, useMemo, useRef, useState } from "react";
import { loadDecoded, type Loaded } from "../stage/loadDecoded";
import { POL_COLORS } from "../lib/moves";
import { fmtDb, fmtInt, monthName, parseDate } from "../lib/format";
import type { StageIndexEntry } from "../lib/types";
import { FixtureTag } from "../components/FixtureTag";

/** The headline finding: in Punjab, wheat waltzes in HV and rice bounces in HH. Every number is
 *  computed here from the stage's per-pass medians, so the text cannot drift from the data. */
export function Finding({ entry }: { entry: StageIndexEntry | null }) {
  const ref = useRef<HTMLElement>(null);
  const [near, setNear] = useState(false);
  const [L, setL] = useState<Loaded | null>(null);
  useEffect(() => {
    // the section only exists once the stage index names a Punjab stage, so observe after that
    if (!entry) return;
    const io = new IntersectionObserver(([e]) => e.isIntersecting && setNear(true), { rootMargin: "500px 0px" });
    if (ref.current) io.observe(ref.current);
    return () => io.disconnect();
  }, [entry]);
  useEffect(() => {
    if (!near || !entry) return;
    loadDecoded(entry.id).then(setL, () => undefined);
  }, [near, entry]);

  const stats = useMemo(() => {
    if (!L || L.hhOnly) return null;
    const { medX, medY } = L.data;
    const dates = L.res.meta.dates;
    const month = (d: string) => new Date(parseDate(d)).getUTCMonth();
    const idx = (ms: number[]) => dates.map((d, i) => (ms.includes(month(d)) ? i : -1)).filter((i) => i >= 0);
    const wheatEarly = idx([10, 11]);
    const wheatPeak = idx([0, 1, 2]);
    const riceLow = idx([5, 6]);
    const ricePeak = idx([6, 7, 8]);
    if (!wheatEarly.length || !wheatPeak.length || !riceLow.length || !ricePeak.length) return null;
    const minOf = (a: Float32Array, is: number[]) => Math.min(...is.map((i) => a[i]));
    const maxOf = (a: Float32Array, is: number[]) => Math.max(...is.map((i) => a[i]));
    return {
      hvClimb: maxOf(medY, wheatPeak) - minOf(medY, wheatEarly),
      hhJump: maxOf(medX, ricePeak) - minOf(medX, riceLow),
      gapPeak: Math.max(...ricePeak.map((i) => medX[i] - medY[i])),
    };
  }, [L]);

  if (!entry) return null;
  return (
    <section ref={ref} className="act act--finding" id="finding">
      <div className="act__inner">
        <div className="finding">
          <div className="finding__text">
            <div className="eyebrow">The finding</div>
            <h2 className="act__title">Same fields, two crops, two partners</h2>
            <p className="act__lede">
              {entry.name}'s farmers grow wheat through the winter and rice through the monsoon, and each crop dances with a different partner.
              {stats ? (
                <>
                  {" "}
                  As wheat grows, the median hectare's <b className="pol pol--hv">HV</b> climbs {fmtDb(stats.hvClimb)} dB into February, then falls at the April
                  harvest: the waltz. Once rice stands in flooded paddies, <b className="pol pol--hh">HH</b> jumps {fmtDb(stats.hhJump)} dB between June and
                  September, because the pulse bounces off water and stalks: the bounce.
                </>
              ) : (
                " Growing wheat adds leaves that HV hears; rice standing in water makes HH bounce."
              )}
            </p>
            <a className="btn btn--primary" href={`#/stage/${entry.id}`} style={{ marginTop: 26 }}>
              Watch {entry.name} dance <span className="arrow">→</span>
            </a>
          </div>
          <div className="finding__chart">{L ? <SeasonChart L={L} /> : <div className="finding__wait" />}</div>
        </div>
      </div>
    </section>
  );
}

function SeasonChart({ L }: { L: Loaded }) {
  const { medX, medY } = L.data;
  const dates = L.res.meta.dates;
  const W = 620;
  const H = 360;
  const m = { l: 40, r: 44, t: 30, b: 34 };
  const t0 = parseDate(dates[0]);
  const t1 = parseDate(dates[dates.length - 1]);
  const X = (d: number) => m.l + ((d - t0) / Math.max(1, t1 - t0)) * (W - m.l - m.r);
  const vals = [...medX, ...medY].filter((v) => Number.isFinite(v));
  const lo = Math.floor((Math.min(...vals) - 1) / 5) * 5;
  const hi = Math.ceil((Math.max(...vals) + 1) / 5) * 5;
  const Y = (v: number) => m.t + ((hi - v) / (hi - lo)) * (H - m.t - m.b);
  const line = (a: Float32Array) => dates.map((d, i) => `${i ? "L" : "M"}${X(parseDate(d)).toFixed(1)},${Y(a[i]).toFixed(1)}`).join("");
  const y0 = new Date(t0).getUTCFullYear();
  const band = (a: number, b: number) => [Math.max(t0, a), Math.min(t1, b)] as const;
  const wheat = band(Date.UTC(y0, 10, 5), Date.UTC(y0 + 1, 3, 20));
  const rice = band(Date.UTC(y0 + 1, 5, 5), Date.UTC(y0 + 1, 9, 25));
  const ticks: number[] = [];
  for (let v = lo; v <= hi; v += 5) ticks.push(v);
  const months: { x: number; label: string }[] = [];
  for (let y = y0, mo = new Date(t0).getUTCMonth() + 1; ; mo++) {
    if (mo > 11) {
      mo = 0;
      y++;
    }
    const t = Date.UTC(y, mo, 1);
    if (t > t1) break;
    if (mo % 2 === 0) months.push({ x: X(t), label: mo === 0 ? String(y) : monthName(mo) });
  }
  const last = dates.length - 1;
  return (
    <figure className="season">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Median HH and HV of the stage over the year">
        {wheat[1] > wheat[0] && (
          <g>
            <rect x={X(wheat[0])} y={m.t - 18} width={X(wheat[1]) - X(wheat[0])} height={H - m.t - m.b + 18} className="season__band" />
            <text x={X(wheat[0]) + 8} y={m.t - 4} className="season__band-label">
              Wheat · the waltz
            </text>
          </g>
        )}
        {rice[1] > rice[0] && (
          <g>
            <rect x={X(rice[0])} y={m.t - 18} width={X(rice[1]) - X(rice[0])} height={H - m.t - m.b + 18} className="season__band" />
            <text x={X(rice[0]) + 8} y={m.t - 4} className="season__band-label">
              Rice · the bounce
            </text>
          </g>
        )}
        {ticks.map((v) => (
          <g key={v}>
            <line x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} className="chart__grid" />
            <text x={m.l - 8} y={Y(v) + 3.5} textAnchor="end" className="chart__tick">
              {fmtDb(v, 0)}
            </text>
          </g>
        ))}
        {months.map((mo) => (
          <text key={mo.x} x={mo.x} y={H - 10} className="chart__tick" textAnchor="middle">
            {mo.label}
          </text>
        ))}
        <path d={line(medY)} className="season__line" style={{ stroke: POL_COLORS.HV }} />
        <path d={line(medX)} className="season__line" style={{ stroke: POL_COLORS.HH }} />
        {dates.map((d, i) => (
          <g key={d}>
            <circle cx={X(parseDate(d))} cy={Y(medX[i])} r={2.6} fill={POL_COLORS.HH} />
            <circle cx={X(parseDate(d))} cy={Y(medY[i])} r={2.6} fill={POL_COLORS.HV} />
          </g>
        ))}
        <text x={X(parseDate(dates[last])) + 7} y={Y(medX[last]) + 4} className="chart__label" style={{ fill: POL_COLORS.HH }}>
          HH
        </text>
        <text x={X(parseDate(dates[last])) + 7} y={Y(medY[last]) + 4} className="chart__label" style={{ fill: POL_COLORS.HV }}>
          HV
        </text>
      </svg>
      <figcaption>
        Median of all {fmtInt(L.data.K)} hectares on each of {dates.length} NISAR passes, dB. {L.res.fixture && <FixtureTag />}
      </figcaption>
    </figure>
  );
}

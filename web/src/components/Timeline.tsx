// Bottom timeline of NISAR passes on the result's track, with the permanent data gap striped (Task B3).
// Picking two passes sets the dates for the next job: createJob(bbox, pair).
import { useState } from "react";
import type { IsoDate } from "../types.ts";
import { DAY_MS, GAP_TEXT, gapWithin, longDate, shortDate, thinLabels, toTime } from "./changeFormat.ts";
import "./Timeline.css";

export type DatePair = [IsoDate, IsoDate];

export interface TimelineProps {
  /** NISAR pass dates on this track (`result.nisar.dates`), any order. */
  dates: IsoDate[];
  /** The two passes to compare; null shows the first and last pass (the server's default pair). */
  value: DatePair | null;
  /** Called with the new pair, earliest first, when the user picks a pass. */
  onChange: (pair: DatePair) => void;
}

/** Inset (% of width) so the end ticks aren't clipped. */
const EDGE_PCT = 3;
/** Minimum spacing (% of width) between date labels. */
const LABEL_GAP_PCT = 7;

interface Pass {
  date: IsoDate;
  t: number;
}

export default function Timeline({ dates, value, onChange }: TimelineProps) {
  // The pass the user clicked most recently stays in the pair; the other one gets replaced.
  const [lastClicked, setLastClicked] = useState<number | null>(null);
  const passes = uniquePasses(dates);

  if (passes.length === 0) {
    return (
      <div className="tl-wrap">
        <div className="tl-head">No NISAR passes on this track yet.</div>
      </div>
    );
  }

  let t0 = passes[0].t;
  let t1 = passes[passes.length - 1].t;
  if (t1 - t0 < DAY_MS) {
    t0 -= 3 * DAY_MS;
    t1 += 3 * DAY_MS;
  }
  const pct = (t: number) => EDGE_PCT + ((t - t0) / (t1 - t0)) * (100 - 2 * EDGE_PCT);

  const pair: [Pass, Pass] | null = value
    ? pairFrom(passes, value)
    : passes.length >= 2
      ? [passes[0], passes[passes.length - 1]]
      : null;
  const isSelected = (p: Pass) => pair !== null && (pair[0].t === p.t || pair[1].t === p.t);

  const pick = (p: Pass) => {
    if (!pair) return;
    setLastClicked(p.t);
    if (isSelected(p)) return;
    const keep = pair.find((q) => q.t === lastClicked) ?? pair[1];
    const next = [keep, p].sort((a, b) => a.t - b.t);
    onChange([next[0].date, next[1].date]);
  };

  const gap = gapWithin(t0, t1);
  const labeled = thinLabels(passes.map((p) => pct(p.t)), LABEL_GAP_PCT);

  return (
    <div className="tl-wrap">
      <div className="tl-head">
        <span>
          NISAR passes on this track.{" "}
          {pair ? (
            <>
              Comparing <b>{shortDate(pair[0].t)}</b> → <b>{shortDate(pair[1].t)}</b>; click a pass to change the pair.
            </>
          ) : (
            "Only one pass, so there is nothing to compare yet."
          )}
        </span>
        {gap && <span>Striped: no NISAR data exists ({GAP_TEXT})</span>}
      </div>
      <div className="tl-track">
        <div className="tl-axis" />
        {gap && (
          <div
            className="tl-gap"
            role="img"
            aria-label={`No NISAR data exists ${GAP_TEXT}`}
            title={`No NISAR data exists ${GAP_TEXT}`}
            style={{ left: `${pct(gap[0])}%`, width: `${pct(gap[1]) - pct(gap[0])}%` }}
          />
        )}
        {passes.map((p, i) => {
          const sel = isSelected(p);
          return (
            <button
              key={p.date}
              type="button"
              className={sel ? "tl-tick sel" : "tl-tick"}
              style={{ left: `${pct(p.t)}%` }}
              aria-pressed={sel}
              aria-label={`NISAR pass ${longDate(p.t)}`}
              title={longDate(p.t)}
              disabled={!pair}
              onClick={() => pick(p)}
            >
              {labeled.has(i) && <span>{shortDate(p.t)}</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function uniquePasses(dates: IsoDate[]): Pass[] {
  const byTime = new Map<number, Pass>();
  for (const date of dates) {
    const t = toTime(date);
    if (Number.isFinite(t) && !byTime.has(t)) byTime.set(t, { date, t });
  }
  return [...byTime.values()].sort((a, b) => a.t - b.t);
}

/** The passes matching `value`; falls back to first/last when a value isn't one of the passes. */
function pairFrom(passes: Pass[], value: DatePair): [Pass, Pass] | null {
  const find = (d: IsoDate) => passes.find((p) => p.t === toTime(d));
  const a = find(value[0]);
  const b = find(value[1]);
  if (a && b && a.t !== b.t) return a.t < b.t ? [a, b] : [b, a];
  return passes.length >= 2 ? [passes[0], passes[passes.length - 1]] : null;
}

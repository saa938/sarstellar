import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { Clock, Tempo } from "./clock";
import { fmtDate, monthName, parseDate } from "../lib/format";
import type { StoryBeat } from "../lib/types";

export interface Score {
  /** fraction of hectares doing move m at beat t: frac[t * M + m] (still and none excluded) */
  frac: Float32Array;
  M: number;
  colors: string[];
  names: string[];
}

interface Props {
  dates: string[];
  clock: Clock;
  beats: { index: number; beat: StoryBeat }[];
  compact?: boolean;
  score?: Score | null;
}

export function useClockBeat(clock: Clock) {
  const [state, setState] = useState({ beat: clock.beat, playing: clock.playing, tempo: clock.tempo });
  useEffect(() => clock.onBeat((beat, playing) => setState({ beat, playing, tempo: clock.tempo })), [clock]);
  return state;
}

export function Timeline({ dates, clock, beats, compact = false, score = null }: Props) {
  const { beat, playing, tempo } = useClockBeat(clock);
  const track = useRef<HTMLDivElement>(null);
  const head = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(0);
  const T = dates.length;
  const t0 = parseDate(dates[0]);
  const t1 = parseDate(dates[T - 1]);
  const pad = 10;
  const xs = useMemo(() => dates.map((d) => pad + ((parseDate(d) - t0) / Math.max(1, t1 - t0)) * Math.max(1, w - 2 * pad)), [dates, w, t0, t1]);
  const xsRef = useRef(xs);
  xsRef.current = xs;

  useLayoutEffect(() => {
    const el = track.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(el.getBoundingClientRect().width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(
    () =>
      clock.subscribe((fr) => {
        const x = xsRef.current;
        if (!head.current || !x.length) return;
        const px = x[fr.i0] + (x[fr.i1] - x[fr.i0]) * fr.e;
        head.current.style.transform = `translateX(${px}px)`;
      }),
    [clock],
  );
  useEffect(() => clock.invalidate(), [xs, clock]);

  const months = useMemo(() => {
    const out: { x: number; label: string; year: boolean }[] = [];
    const d0 = new Date(t0);
    let y = d0.getUTCFullYear();
    let m = d0.getUTCMonth() + 1;
    for (;;) {
      if (m > 11) {
        m = 0;
        y++;
      }
      const t = Date.UTC(y, m, 1);
      if (t > t1) break;
      out.push({ x: pad + ((t - t0) / Math.max(1, t1 - t0)) * Math.max(1, w - 2 * pad), label: m === 0 ? String(y) : monthName(m), year: m === 0 });
      m++;
    }
    return out;
  }, [t0, t1, w]);

  const seekFromX = (clientX: number) => {
    if (!track.current) return clock.t;
    const r = track.current.getBoundingClientRect();
    const px = clientX - r.left;
    const x = xsRef.current;
    if (px <= x[0]) return 0;
    if (px >= x[T - 1]) return T - 1;
    for (let i = 0; i < T - 1; i++) {
      if (px >= x[i] && px <= x[i + 1]) return i + (px - x[i]) / Math.max(1e-6, x[i + 1] - x[i]);
    }
    return 0;
  };
  const dragging = useRef(false);
  const onDown = (e: React.PointerEvent) => {
    dragging.current = true;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    clock.pause();
    clock.seek(seekFromX(e.clientX));
  };
  const onMove = (e: React.PointerEvent) => {
    if (dragging.current) clock.seek(seekFromX(e.clientX));
  };
  const onUp = () => {
    if (!dragging.current) return;
    dragging.current = false;
    clock.seek(Math.round(clock.t));
  };

  return (
    <div className={`timeline ${compact ? "timeline--compact" : ""} ${score ? "timeline--score" : ""}`}>
      <div className="timeline__controls">
        <button className="btn-play" onClick={() => clock.toggle()} aria-label={playing ? "Pause" : "Play"} title="Space">
          {playing ? (
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden>
              <rect x="6" y="5" width="4" height="14" rx="1" fill="currentColor" />
              <rect x="14" y="5" width="4" height="14" rx="1" fill="currentColor" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden>
              <path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5z" fill="currentColor" />
            </svg>
          )}
        </button>
        <div className="seg" role="group" aria-label="Tempo">
          {(["slow", "normal", "fast"] as Tempo[]).map((tp) => (
            <button key={tp} className={tempo === tp ? "is-on" : ""} onClick={() => clock.setTempo(tp)}>
              {tp === "slow" ? "Slow" : tp === "normal" ? "Normal" : "Fast"}
            </button>
          ))}
        </div>
        <div className="timeline__step">
          <button className="btn-icon" onClick={() => clock.step(-1)} aria-label="Previous pass" title="Left arrow">
            <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden>
              <path d="M15 6l-6 6 6 6" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" />
            </svg>
          </button>
          <button className="btn-icon" onClick={() => clock.step(1)} aria-label="Next pass" title="Right arrow">
            <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden>
              <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" />
            </svg>
          </button>
        </div>
        <div className="timeline__now">
          <span className="timeline__date">{fmtDate(dates[beat])}</span>
          <span className="timeline__pass">
            pass {beat + 1} of {T}
          </span>
        </div>
      </div>
      <div className="timeline__track" ref={track} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}>
        <div className="timeline__rail" />
        {score && <ScoreStrip score={score} xs={xs} />}
        {months.map((m) => (
          <div key={`${m.label}${m.x}`} className={`timeline__month ${m.year ? "is-year" : ""}`} style={{ transform: `translateX(${m.x}px)` }}>
            <span>{m.label}</span>
          </div>
        ))}
        {xs.map((x, i) => (
          <button
            key={i}
            className={`timeline__beat ${i === beat ? "is-now" : ""} ${i < beat ? "is-past" : ""}`}
            style={{ transform: `translateX(${x}px)` }}
            onPointerDown={(e) => e.stopPropagation()}
            onClick={() => {
              clock.pause();
              clock.seek(i);
            }}
            aria-label={`Pass ${i + 1}: ${fmtDate(dates[i])}`}
            title={fmtDate(dates[i])}
          />
        ))}
        {beats.map((b) => (
          <div key={b.index + b.beat.caption} className={`timeline__story ${b.index <= beat ? "is-past" : ""}`} style={{ transform: `translateX(${xs[b.index] ?? 0}px)` }} title={b.beat.caption}>
            <i />
          </div>
        ))}
        <div className="timeline__head" ref={head}>
          <i />
        </div>
      </div>
    </div>
  );
}

function ScoreStrip({ score, xs }: { score: Score; xs: number[] }) {
  const { frac, M, colors, names } = score;
  const T = xs.length;
  let max = 0;
  for (let t = 0; t < T; t++) {
    let s = 0;
    for (let m = 0; m < M; m++) s += frac[t * M + m];
    max = Math.max(max, s);
  }
  const H = 18;
  const w = Math.max(3, Math.min(9, (xs[T - 1] - xs[0]) / Math.max(1, T) * 0.5));
  return (
    <svg className="timeline__score" width="100%" height={H} aria-label="Choreography score: share of hectares doing each move on each pass">
      {xs.map((x, t) => {
        let y = H;
        const segs = [];
        for (let m = 0; m < M; m++) {
          const f = frac[t * M + m];
          if (f <= 0) continue;
          const h = Math.max(1, (f / Math.max(max, 1e-6)) * (H - 2));
          y -= h;
          segs.push(<rect key={m} x={x - w / 2} y={y} width={w} height={h} rx={1} fill={colors[m]}><title>{`${names[m]}: ${(f * 100).toFixed(1)}% of hectares`}</title></rect>);
        }
        return <g key={t}>{segs}</g>;
      })}
    </svg>
  );
}

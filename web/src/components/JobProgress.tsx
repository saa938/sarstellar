// Live job runner (useLiveJob) and its progress panel (JobProgress).
// Jobs start from a user action, never from an effect, so StrictMode can't double-POST against the
// per-IP job limit.
import { useCallback, useEffect, useRef, useState } from "react";
import { createJob, pollJob } from "../api.ts";
import type { Bbox, IsoDate, Result } from "../types.ts";
import { validateBox } from "./box.ts";
import "./DrawBox.css";

/** Pipeline stages in order (spec: "finding passes -> reading passes -> testing -> explaining"). */
export const STAGES = [
  "Finding passes",
  "Reading passes",
  "Testing every hectare for change",
  "Explaining what changed",
] as const;
// run_box reports 0.1 search, 0.2-0.7 reads, 0.8 test, 0.9 explain (plan Task A6).
const STAGE_STARTS = [0, 0.2, 0.8, 0.9];

/** Index into STAGES for a job's progress fraction. */
export function stageIndex(progress: number): number {
  let i = 0;
  while (i + 1 < STAGE_STARTS.length && progress >= STAGE_STARTS[i + 1]) i++;
  return i;
}

export type LiveJobState =
  | { status: "idle" }
  | { status: "running"; progress: number; message: string }
  | { status: "done"; areas: number; message: string | null }
  | { status: "error"; message: string };

export interface LiveJob {
  state: LiveJobState;
  running: boolean;
  /** Validate the box, submit it, and poll until done or error. Replaces any job in flight. */
  start: (bbox: Bbox, dates?: [IsoDate, IsoDate]) => Promise<void>;
  /** Stop polling (silently) and hide the panel. */
  cancel: () => void;
  /** Hide a finished or failed job's panel. */
  reset: () => void;
}

const SENDING = "Sending your box to the analysis server";

export function useLiveJob(onResult: (result: Result) => void, pollIntervalMs = 1000): LiveJob {
  const [state, setState] = useState<LiveJobState>({ status: "idle" });
  const current = useRef<AbortController | null>(null);
  const onResultRef = useRef(onResult);
  useEffect(() => {
    onResultRef.current = onResult;
  });
  useEffect(() => () => current.current?.abort(), []);

  const start = useCallback(
    async (bbox: Bbox, dates?: [IsoDate, IsoDate]) => {
      const invalid = validateBox(bbox);
      if (invalid) {
        setState({ status: "error", message: invalid });
        return;
      }
      current.current?.abort();
      const ctl = new AbortController();
      current.current = ctl;
      const live = () => current.current === ctl && !ctl.signal.aborted;
      setState({ status: "running", progress: 0, message: SENDING });
      try {
        const { job_id } = await createJob(bbox, dates, ctl.signal);
        const result = await pollJob(
          job_id,
          (job) => {
            if (live() && job.status !== "done") {
              setState({ status: "running", progress: clamp01(job.progress), message: job.message });
            }
          },
          pollIntervalMs,
          { signal: ctl.signal },
        );
        if (!live()) return;
        current.current = null;
        setState({ status: "done", areas: result.areas.length, message: result.message });
        onResultRef.current(result);
      } catch (err) {
        // Cancelled, unmounted or replaced by a newer job: say nothing.
        if (!live() || (err instanceof Error && err.name === "AbortError")) return;
        current.current = null;
        // Server messages (job errors, 422/429/503 details) and the poll timeout are shown verbatim.
        const message = err instanceof Error && err.message ? err.message : "The analysis failed.";
        setState({ status: "error", message });
      }
    },
    [pollIntervalMs],
  );

  const cancel = useCallback(() => {
    const ctl = current.current;
    current.current = null;
    ctl?.abort();
    setState({ status: "idle" });
  }, []);

  const reset = useCallback(() => {
    if (!current.current) setState({ status: "idle" });
  }, []);

  return { state, running: state.status === "running", start, cancel, reset };
}

export interface JobProgressProps {
  state: LiveJobState;
  onCancel: () => void;
  onDismiss: () => void;
}

export function JobProgress({ state, onCancel, onDismiss }: JobProgressProps) {
  if (state.status === "idle") return null;

  if (state.status === "error") {
    return (
      <section className="job job-error" aria-label="Live analysis">
        <p role="alert">{state.message}</p>
        <button type="button" className="db-btn db-small" onClick={onDismiss}>
          Dismiss
        </button>
      </section>
    );
  }

  if (state.status === "done") {
    const n = state.areas;
    return (
      <section className="job job-done" aria-label="Live analysis">
        <p className="job-title">
          Analysis complete · {n === 0 ? "no change areas" : `${n} change ${n === 1 ? "area" : "areas"}`}
        </p>
        {state.message && <p className="job-note">{state.message}</p>}
        <button type="button" className="db-btn db-small" onClick={onDismiss}>
          OK
        </button>
      </section>
    );
  }

  const pct = Math.round(state.progress * 100);
  const at = stageIndex(state.progress);
  return (
    <section className="job" aria-label="Live analysis" aria-busy="true">
      <div className="job-bar" role="progressbar" aria-label="Analysis progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
        <i style={{ width: `${Math.max(pct, 3)}%` }} />
      </div>
      <ol className="job-stages">
        {STAGES.map((label, i) => (
          <li key={label} className={i < at ? "done" : i === at ? "on" : undefined} aria-current={i === at ? "step" : undefined}>
            {label}
          </li>
        ))}
      </ol>
      {state.message && state.message !== STAGES[at] && (
        <p className="job-msg" aria-live="polite">
          {state.message}
        </p>
      )}
      <button type="button" className="db-btn db-small" onClick={onCancel}>
        Cancel
      </button>
    </section>
  );
}

function clamp01(x: number): number {
  return Number.isFinite(x) ? Math.min(1, Math.max(0, x)) : 0;
}

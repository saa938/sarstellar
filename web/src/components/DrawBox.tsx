// "Draw a box anywhere": rectangle drawing on the map, a live size readout, the 20 km rule enforced
// before submit, and the live job (progress, server messages) via useLiveJob/JobProgress.
import type { Map as MaplibreMap } from "maplibre-gl";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Bbox, IsoDate, Result } from "../types.ts";
import { EMPTY_BOX_MESSAGE, boxSize, formatSize, validateBox, type BoxDrawer, type BoxListener } from "./box.ts";
import { JobProgress, useLiveJob } from "./JobProgress.tsx";
import "./DrawBox.css";

export interface DrawBoxProps {
  /** The MapLibre map the box is drawn on; null until the map exists (the button stays disabled). */
  map: MaplibreMap | null;
  /** Two dates picked on the timeline, sent with the job; omit to let the server choose. */
  dates?: [IsoDate, IsoDate];
  /** Receives the finished Result, which should replace what the map currently shows. */
  onResult: (result: Result) => void;
  /** Drawing tool factory; defaults to terra-draw (loaded on first use). Tests pass a fake. */
  createDrawer?: (map: MaplibreMap) => BoxDrawer | Promise<BoxDrawer>;
}

type Phase = "idle" | "drawing" | "drawn";

const TOOL_ERROR = "The drawing tool didn't load. Reload the page and try again.";

const loadTerraDraw = (map: MaplibreMap) =>
  import("./terraDrawBox.ts").then((m) => m.createTerraDrawBoxDrawer(map));

export function DrawBox({ map, dates, onResult, createDrawer = loadTerraDraw }: DrawBoxProps) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [box, setBox] = useState<Bbox | null>(null);
  const [toolError, setToolError] = useState<string | null>(null);
  const pending = useRef<Promise<BoxDrawer> | null>(null);
  const drawer = useRef<BoxDrawer | null>(null);

  const job = useLiveJob((result) => {
    // The result's own overlays now show this box.
    drawer.current?.clear();
    setBox(null);
    onResult(result);
  });

  // One drawer per map; released when the map changes or DrawBox unmounts.
  useEffect(
    () => () => {
      const p = pending.current;
      pending.current = null;
      drawer.current = null;
      p?.then(
        (d) => d.destroy(),
        () => {},
      );
    },
    [map],
  );

  const listener = useCallback<BoxListener>((bbox, done) => {
    setBox(bbox);
    if (done) setPhase(bbox ? "drawn" : "drawing");
  }, []);

  const startDrawing = async () => {
    if (!map) return;
    setBox(null);
    setToolError(null);
    setPhase("drawing");
    pending.current ??= Promise.resolve().then(() => createDrawer(map));
    const p = pending.current;
    try {
      const d = await p;
      if (pending.current !== p) return; // map changed or unmounted meanwhile
      drawer.current = d;
      d.start(listener);
    } catch {
      if (pending.current === p) pending.current = null;
      setPhase("idle");
      setToolError(TOOL_ERROR);
    }
  };

  const cancelDrawing = () => {
    drawer.current?.clear();
    setBox(null);
    setPhase("idle");
  };

  const boxError = box ? validateBox(box) : null;

  const submit = () => {
    if (!box || boxError || job.running) return;
    setPhase("idle");
    void job.start(box, dates);
  };

  // While drawing, a zero-size box just means "second corner not placed yet".
  const showError = boxError && !(phase === "drawing" && boxError === EMPTY_BOX_MESSAGE);
  const showSize = boxError !== EMPTY_BOX_MESSAGE && (phase !== "idle" || job.running);

  return (
    <div className="drawbox">
      {phase === "idle" && (
        <button
          type="button"
          className="db-btn db-primary"
          onClick={startDrawing}
          disabled={!map || job.running}
          title={map ? undefined : "The map is still loading"}
        >
          Draw a box anywhere
        </button>
      )}
      {phase === "drawing" && <p className="db-hint">Click one corner, then the opposite corner (or drag). Up to 20 km a side.</p>}
      {showSize && box && (
        <div className={`db-size${boxError ? " db-over" : ""}`} aria-live="polite">
          <span>This box</span>
          <b>{formatSize(boxSize(box))}</b>
        </div>
      )}
      {showError && (
        <p role="alert" className="db-error">
          {boxError}
        </p>
      )}
      {toolError && (
        <p role="alert" className="db-error">
          {toolError}
        </p>
      )}
      {phase === "drawing" && (
        <button type="button" className="db-btn db-small" onClick={cancelDrawing}>
          Cancel drawing
        </button>
      )}
      {phase === "drawn" && (
        <div className="db-actions">
          <button type="button" className="db-btn db-primary" onClick={submit} disabled={!!boxError || job.running}>
            Analyze this box
          </button>
          <button type="button" className="db-btn db-small" onClick={startDrawing}>
            Redraw
          </button>
        </div>
      )}
      <JobProgress state={job.state} onCancel={job.cancel} onDismiss={job.reset} />
    </div>
  );
}

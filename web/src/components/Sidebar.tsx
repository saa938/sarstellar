// Left panel (mockup): draw-a-box slot, stories list, facts about the current box, legend, "How sure are we?".
import type { ReactNode } from "react";
import { formatDateRange } from "../areas.ts";
import type { Agreement, Result, StoryIndexEntry } from "../types.ts";
import { boxSize } from "./box.ts";
import { Legend } from "./Legend.tsx";

/** Shown wherever spike-derived stand-in data (`fixture: true`) is on screen. */
export function ExampleTag() {
  return (
    <span className="example-tag" title="Saved example from early test runs, not a final pipeline result">
      Example data
    </span>
  );
}

export interface SidebarProps {
  /** Shown at the top of the panel: the "Draw a box anywhere" control. */
  actions?: ReactNode;
  /** null while the stories index is loading. */
  stories: readonly StoryIndexEntry[] | null;
  activeStoryId: string | null;
  onSelectStory: (id: string) => void;
  result: Result | null;
  hidden: ReadonlySet<Agreement>;
  onToggleAgreement: (agreement: Agreement) => void;
}

export function Sidebar({ actions, stories, activeStoryId, onSelectStory, result, hidden, onToggleAgreement }: SidebarProps) {
  return (
    <aside className="side" aria-label="Analysis workspace">
      <div className="sidebar-actions">{actions}</div>

      <div className="label sidebar-section-title">Saved stories <span>{stories?.length ?? ""}</span></div>
      {stories === null && <p className="hint">Loading stories…</p>}
      {stories?.length === 0 && <p className="hint">No stories are available right now.</p>}
      {stories?.map((s) => (
        <button
          key={s.id}
          type="button"
          className={s.id === activeStoryId ? "story active" : "story"}
          aria-current={s.id === activeStoryId ? "true" : undefined}
          onClick={() => onSelectStory(s.id)}
        >
          <b>{s.title}</b>
          <small>{s.place}</small>
          <span className="story-date">{formatDateRange(s.dates)}</span>
          {s.fixture && <ExampleTag />}
        </button>
      ))}

      {result && (
        <>
          <div className="label">This box</div>
          <BoxFacts result={result} />
          <div className="label legend-heading">Detected change</div>
          <p className="section-note">Toggle layers on the map</p>
          <Legend areas={result.areas} hidden={hidden} onToggle={onToggleAgreement} />
        </>
      )}

      <details className="method-notes">
        <summary>How sure are we?</summary>
        <p>Every 1-hectare block gets a statistical test across all passes. We only call it change when the test holds up
        after correcting for testing many blocks at once (false discovery rate 5%), the radar echo moved by at
        least 2 dB, and the changed blocks cover at least 3 hectares. The Scorecard page shows how often this flags
        ground we know is stable.</p>
      </details>
    </aside>
  );
}

function BoxFacts({ result }: { result: Result }) {
  const { nisar, s1 } = result;
  const arrow = nisar.direction === "A" ? "↑" : "↓";
  return (
    <div className="facts" role="group" aria-label="This box">
      <div>
        <span>Area</span>
        <b>{Math.round(boxSize(result.bbox).areaKm2).toLocaleString("en-US")} km²</b>
      </div>
      <div>
        <span>NISAR passes (L-band)</span>
        <b>
          {nisar.dates.length} · track {nisar.track} {arrow}
        </b>
      </div>
      <div>
        <span>Sentinel-1 passes (C-band)</span>
        <b>{s1 ? s1.dates.length : "none"}</b>
      </div>
      <div>
        <span>Compared</span>
        <b>{formatDateRange(nisar.dates)}</b>
      </div>
    </div>
  );
}

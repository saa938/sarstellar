// Analysis controls, example selection, acquisition metadata and detection layers.
import type { ReactNode } from "react";
import { formatDateRange } from "../areas.ts";
import type { Agreement, Result, StoryIndexEntry } from "../types.ts";
import { boxSize } from "./box.ts";
import { Legend } from "./Legend.tsx";

/** Shown wherever spike-derived stand-in data (`fixture: true`) is on screen. */
export function ExampleTag() {
  return (
    <span className="example-tag" title="Spike-derived fixture; not a final pipeline result">
      Test fixture
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
  /** Map layer opacity, normalized to 0..1. */
  layerOpacity?: number;
  onOpacityChange?: (opacity: number) => void;
  layerControlsEnabled?: boolean;
}

export function Sidebar({ actions, stories, activeStoryId, onSelectStory, result, hidden, onToggleAgreement,
  layerOpacity = 1, onOpacityChange, layerControlsEnabled = true }: SidebarProps) {
  const opacityPercent = Math.round(Math.max(0, Math.min(1, layerOpacity)) * 100);
  return (
    <aside className="side" aria-label="Analysis workspace">
      <div className="sidebar-actions">{actions}</div>

      <div className="label sidebar-section-title">Examples <span>{stories?.length ?? ""}</span></div>
      {stories === null && <p className="hint">Loading examples…</p>}
      {stories?.length === 0 && <p className="hint">No examples available.</p>}
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
          <div className="label legend-heading">Layers</div>
          <p className="section-note">Area labels · ha</p>
          <Legend areas={result.areas} hidden={hidden} onToggle={onToggleAgreement} disabled={!layerControlsEnabled} />
          {onOpacityChange && (
            <label className="layer-opacity">
              <span>Area opacity <b>{opacityPercent}%</b></span>
              <input type="range" min={0} max={100} value={opacityPercent}
                aria-label="Area opacity" aria-valuetext={`${opacityPercent}%`}
                disabled={!layerControlsEnabled}
                onChange={(event) => onOpacityChange(Number(event.target.value) / 100)} />
            </label>
          )}
          {!layerControlsEnabled && <p className="section-note">Area controls apply to the Detected areas view.</p>}
          <div className="label">Acquisitions</div>
          <BoxFacts result={result} />
          <details className="coordinates">
            <summary>Coordinates</summary>
            <p className="hint">Longitude / latitude · WGS 84 (°)</p>
            <div className="facts" role="group" aria-label="AOI coordinates">
              {(["West", "South", "East", "North"] as const).map((label, index) =>
                <div key={label}><span>{label}</span><b>{String(result.bbox[index])}</b></div>)}
            </div>
          </details>
        </>
      )}

      <details className="method-notes">
        <summary>Detection criteria</summary>
        <p>1 ha blocks; BH-FDR q = 0.05; |relative Δ| ≥ 2 dB; minimum area 3 ha.</p>
        <p><a href="#/scorecard">Validation scorecard</a></p>
      </details>
    </aside>
  );
}

function BoxFacts({ result }: { result: Result }) {
  const { nisar, s1 } = result;
  const direction = nisar.direction === "A" ? "ascending" : "descending";
  return (
    <div className="facts" role="group" aria-label="Acquisition metadata">
      <div>
        <span>AOI area</span>
        <b>{Math.round(boxSize(result.bbox).areaKm2).toLocaleString("en-US")} km²</b>
      </div>
      <div>
        <span>NISAR acquisitions</span>
        <b>
          {nisar.dates.length} · track {nisar.track} · {direction}
        </b>
      </div>
      <div>
        <span>NISAR dates</span>
        <b>{formatDateRange(nisar.dates) || "Unavailable"}</b>
      </div>
      <div>
        <span>Sentinel-1 acquisitions</span>
        <b>{s1 ? `${s1.dates.length} · track ${s1.track}` : "Unavailable"}</b>
      </div>
      <div>
        <span>Sentinel-1 dates</span>
        <b>{s1 ? formatDateRange(s1.dates) || "Unavailable" : "Unavailable"}</b>
      </div>
    </div>
  );
}

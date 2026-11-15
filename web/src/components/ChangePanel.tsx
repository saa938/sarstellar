// Right-hand panel for one clicked change area (Task B3), laid out as in docs/mockups/app-mockup.html.
import { AGREEMENT_COLORS, type ChangeArea, type ConfidenceLabel, type Evidence, type Result } from "../types.ts";
import {
  classTitle,
  formatHa,
  formatNumber,
  formatP,
  longDate,
  ordinal,
  toTime,
  withUnit,
} from "./changeFormat.ts";
import { DETECTION_LABELS } from "./Legend.tsx";
import SeriesChart from "./SeriesChart.tsx";
import "./ChangePanel.css";

/** The parts of the Result the panel reads (pass the whole Result). */
export type ChangePanelResult = Pick<Result, "fixture" | "people" | "exports">;

export interface ChangePanelProps {
  /** The clicked change area. */
  area: ChangeArea;
  /** The Result the area belongs to: drives the Example data tag, the people block and the exports. */
  result: ChangePanelResult;
  /** When given, a close button is shown (e.g. to return to the story intro). */
  onClose?: () => void;
}

const CONF_COLOR: Record<ConfidenceLabel, string> = { High: "var(--ok)", Medium: "var(--warn)", Low: "var(--muted)" };
const EXPORTS = [
  { key: "geotiff", label: "GeoTIFF", hint: "Change map: agreement and per-band dB changes on the 1-ha grid" },
  { key: "csv", label: "CSV", hint: "One row per change area" },
  { key: "notebook", label: "Notebook", hint: "Jupyter notebook that reruns this analysis" },
] as const;
const MAX_TRACTS = 3;

export default function ChangePanel({ area, result, onClose }: ChangePanelProps) {
  const title = classTitle(area.class);
  const confidence = Math.min(1, Math.max(0, Number.isFinite(area.confidence) ? area.confidence : 0));
  const changeT = area.change_date ? toTime(area.change_date) : NaN;

  return (
    <section className="cp" aria-label={`Change area: ${title}`}>
      <div className="cp-chips">
        <span className="cp-chip" data-agreement={area.agreement}
          style={{ borderLeftColor: AGREEMENT_COLORS[area.agreement], color: "var(--text)" }}>
          {DETECTION_LABELS[area.agreement]}
        </span>
        {result.fixture && (
          <span className="cp-example" title="Spike-derived fixture; not a final pipeline result">
            Test fixture
          </span>
        )}
        {onClose && (
          <button type="button" className="cp-close" aria-label="Back to areas" onClick={onClose}>
            ← Areas
          </button>
        )}
      </div>
      <div className="cp-label">Classification (rule-based)</div>
      <h2 className="cp-title">{title}</h2>
      <p className="cp-note">Provisional class hypothesis · area {area.id}</p>

      <div className="cp-conf">
        <span>Detection confidence</span>
        <div className="cp-bar" aria-hidden="true">
          <i style={{ width: `${confidence * 100}%`, background: CONF_COLOR[area.confidence_label] ?? "var(--muted)" }} />
        </div>
        <span>
          <b>{area.confidence_label}</b> · {formatP(area.p_value)} · {formatHa(area.area_ha)} ha
        </span>
      </div>
      {Number.isFinite(changeT) && <p className="cp-when">First flagged acquisition: {longDate(changeT)} (UTC).</p>}
      <ResultExports files={result.exports} />

      <section aria-label="Measurements">
        <h3 className="cp-label">Measurements</h3>
        {area.evidence.length > 0 ? (
          <ul className="cp-ev" aria-label="Measurements">
            {area.evidence.map((ev, i) => (
              <EvidenceItem key={`${ev.label}-${i}`} ev={ev} />
            ))}
          </ul>
        ) : <p className="cp-note">No measurements recorded for this area.</p>}
      </section>

      <h3 className="cp-label">Backscatter time series (dB)</h3>
      <SeriesChart series={area.series} changeDate={area.change_date} />

      {area.plain_text && (
        <section aria-label="Interpretation">
          <h3 className="cp-label">Interpretation</h3>
          <div className="cp-plain">
            {area.plain_text}
            <small>Verify the class hypothesis against independent reference data.</small>
          </div>
        </section>
      )}
      <People tracts={result.people.svi_tracts} />
    </section>
  );
}

/** Dataset-level files; usable in the overview even when no change area is selected. */
export function ResultExports({ files }: { files: Result["exports"] }) {
  const anyExport = EXPORTS.some((e) => files[e.key]);
  if (!anyExport) return <p className="cp-note">Exports unavailable for this result.</p>;
  return (
    <section aria-label="Exports">
      <h3 className="cp-label">Exports</h3>
      <div className="cp-exports">
        {EXPORTS.map((e) => {
          const url = files[e.key];
          return url ? (
            <a key={e.key} className="cp-btn" href={url} download title={e.hint}>
              {e.label}
            </a>
          ) : (
            <button key={e.key} type="button" className="cp-btn" disabled title={`${e.hint} (not available for this result)`}>
              {e.label}
            </button>
          );
        })}
      </div>
    </section>
  );
}

function EvidenceItem({ ev }: { ev: Evidence }) {
  const value =
    typeof ev.value === "number" && Number.isFinite(ev.value)
      ? withUnit(formatNumber(ev.value, ev.unit), ev.unit)
      : typeof ev.value === "string" && ev.value
        ? withUnit(ev.value, ev.unit)
        : null;
  const ci =
    ev.ci && ev.ci.every((x) => typeof x === "number" && Number.isFinite(x))
      ? `95% CI ${formatNumber(ev.ci[0], ev.unit)} to ${withUnit(formatNumber(ev.ci[1], ev.unit), ev.unit)}`
      : null;
  return (
    <li>
      <b>{ev.label}</b>
      {value && (
        <>
          : <b>{value}</b>
        </>
      )}
      {ci && <span className="cp-ci"> ({ci})</span>}
      {ev.note && <span className="cp-src">{ev.note}</span>}
    </li>
  );
}

function People({ tracts }: { tracts: Result["people"]["svi_tracts"] }) {
  // SVI uses -999 for "no data"; keep only real percentile ranks.
  const ranked = tracts
    .filter((t) => typeof t.rpl_themes === "number" && t.rpl_themes >= 0 && t.rpl_themes <= 1)
    .sort((a, b) => b.rpl_themes - a.rpl_themes);
  if (ranked.length === 0) return null;
  const more = ranked.length - MAX_TRACTS;
  return (
    <>
      <h3 className="cp-label">Context: CDC SVI 2022</h3>
      <div className="cp-who">
        <p>AOI census tracts, sorted by social vulnerability percentile. Higher values indicate greater relative vulnerability.</p>
        <ul aria-label="Census tracts">
          {ranked.slice(0, MAX_TRACTS).map((t) => (
            <li key={t.geoid}>
              <span>{t.name}</span>
              <b>{ordinal(Math.round(t.rpl_themes * 100))} percentile</b>
            </li>
          ))}
        </ul>
        {more > 0 && <small>{`${more} additional ${more === 1 ? "tract" : "tracts"} in the AOI`}</small>}
      </div>
    </>
  );
}

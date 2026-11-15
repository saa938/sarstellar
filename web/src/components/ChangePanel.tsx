// Right-hand panel for one clicked change area (Task B3), laid out as in docs/mockups/app-mockup.html.
import { AGREEMENT_COLORS, type ChangeArea, type Evidence, type Result, type Scorecard } from "../types.ts";
import { radarTrust } from "./radarTrust.ts";
import { formatDateRange } from "../areas.ts";
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
import { displayRuleText, guidanceFor, supportingEvidence } from "./selectedAreaGuidance.ts";
import SeriesChart from "./SeriesChart.tsx";
import "./ChangePanel.css";

/** The parts of the Result the panel reads (pass the whole Result). */
export type ChangePanelResult = Pick<Result, "fixture" | "people" | "exports"> &
  Partial<Pick<Result, "nisar" | "s1">>;

export interface ChangePanelProps {
  /** The clicked change area. */
  area: ChangeArea;
  /** The Result the area belongs to: drives the Example data tag, the people block and the exports. */
  result: ChangePanelResult;
  /** When given, a close button is shown (e.g. to return to the story intro). */
  onClose?: () => void;
  /** Held-out benchmark; drives the "Which radar should I trust?" verdict when loaded. */
  scorecard?: Pick<Scorecard, "equal_recall" | "holdout_states"> | null;
}

const EXPORTS = [
  { key: "geotiff", label: "GeoTIFF", hint: "Change map: agreement and per-band dB changes on the 1-ha grid" },
  { key: "csv", label: "CSV", hint: "One row per change area" },
  { key: "notebook", label: "Notebook", hint: "Jupyter notebook that reruns this analysis" },
] as const;
const MAX_TRACTS = 3;

export default function ChangePanel({ area, result, onClose, scorecard }: ChangePanelProps) {
  const guidance = guidanceFor(area.class);
  const trust = radarTrust(area, scorecard?.equal_recall);
  const support = supportingEvidence(area.evidence);
  const changeT = area.change_date ? toTime(area.change_date) : NaN;

  return (
    <section className="cp" aria-label="Selected change area">
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
      <h2 className="cp-title">Change detected</h2>
      <p className="cp-note">Area {area.id}</p>
      <div className="cp-workflow">
        <section className="cp-question" aria-label="What changed?">
          <h3 className="cp-question-title"><span className="cp-question-number">1</span> What changed?</h3>
          <p className="cp-observed">Radar signal changed across <b>{formatHa(area.area_ha)} ha</b>.</p>
          <p className="cp-caveat">The radar detection does not establish a physical cause.</p>
        </section>
        <section className="cp-question" aria-label="When?">
          <h3 className="cp-question-title"><span className="cp-question-number">2</span> When?</h3>
          <p className="cp-when">{Number.isFinite(changeT)
            ? `First flagged acquisition: ${longDate(changeT)} (UTC).`
            : "No onset acquisition identified."}{" "}
            <span className="cp-caveat">Observation timing; no event date is established.</span></p>
          {(result.nisar?.dates.length || result.s1?.dates.length) ?
            <details className="cp-acquisition-context">
              <summary>Acquisition windows</summary>
              {result.nisar?.dates.length ?
                <p className="cp-note">NISAR window: {formatDateRange(result.nisar.dates)}</p> : null}
              {result.s1?.dates.length ?
                <p className="cp-note">Sentinel-1 window: {formatDateRange(result.s1.dates)}</p> : null}
            </details> : null}
        </section>
        <section className="cp-question" aria-label="Why this hypothesis?">
          <h3 className="cp-question-title"><span className="cp-question-number">3</span> Why this hypothesis?</h3>
          <p className="cp-hypothesis">{guidance.hypothesis}</p>
          <p className="cp-caveat">Provisional rule-based interpretation.</p>
          {support.length > 0 ? <ul className="cp-support" aria-label="Supporting rule evidence">
            {support.map((ev, i) => <EvidenceItem key={`${ev.label}-${i}`} ev={ev} compact />)}
          </ul> : <p className="cp-note">No supporting rule measurements supplied.</p>}
        </section>
        <section className="cp-question cp-trust" data-tone={trust.tone} aria-label="Which radar should I trust?">
          <h3 className="cp-question-title"><span className="cp-question-number">4</span> Which radar should I trust?</h3>
          <p className="cp-trust-headline">{trust.headline}</p>
          <p className="cp-note">{trust.detail}</p>
          {trust.tone !== "none" && <p className="cp-caveat">From the <a href="#/scorecard">held-out benchmark</a>
            {scorecard?.holdout_states.length ? ` (${scorecard.holdout_states.length} states never used for fitting)` : ""}; it assumes the cause hypothesis above.</p>}
        </section>
        <section className="cp-question" aria-label="What to check next?">
          <h3 className="cp-question-title"><span className="cp-question-number">5</span> What to check next?</h3>
          <ul className="cp-next" aria-label="Verification steps">
            {guidance.checks.map((check) => <li key={check}>{check}</li>)}
          </ul>
          <p className="cp-caveat">{guidance.caveat}</p>
        </section>
      </div>

      <ResultExports files={result.exports} />
      <details className="cp-technical">
        <summary>Technical statistics</summary>
        <section aria-label="Detector statistics">
        <dl className="cp-summary-facts">
          <div><dt>Area</dt><dd>{formatHa(area.area_ha)} ha</dd></div>
          <div><dt>Rule class</dt><dd>{classTitle(area.class)}</dd></div>
          <div><dt>Nominal detector p-value</dt><dd>{formatP(area.p_value)}</dd></div>
          <div><dt>Heuristic confidence label</dt><dd>{area.confidence_label}</dd></div>
        </dl>
        <p className="cp-note">The detector p-value is not a class probability. The confidence label is heuristic, not a calibrated probability.</p>
        </section>
      </details>

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
            {displayRuleText(area.plain_text)}
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

function EvidenceItem({ ev, compact = false }: { ev: Evidence; compact?: boolean }) {
  const value =
    typeof ev.value === "number" && Number.isFinite(ev.value)
      ? withUnit(formatNumber(ev.value, ev.unit), ev.unit)
      : typeof ev.value === "string" && ev.value
        ? withUnit(displayRuleText(ev.value), ev.unit)
        : null;
  const ci =
    ev.ci && ev.ci.every((x) => typeof x === "number" && Number.isFinite(x))
      ? `95% CI ${formatNumber(ev.ci[0], ev.unit)} to ${withUnit(formatNumber(ev.ci[1], ev.unit), ev.unit)}`
      : null;
  return (
    <li>
      <b>{displayRuleText(ev.label)}</b>
      {value && (
        <>
          : <b>{value}</b>
        </>
      )}
      {!compact && ci && <span className="cp-ci"> ({ci})</span>}
      {!compact && ev.note && <span className="cp-src">{ /\bdocs[\\/]/i.test(ev.note)
        ? <a href="#/about">Methods and rule criteria</a>
        : displayRuleText(ev.note)}</span>}
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

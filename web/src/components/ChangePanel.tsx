// Right-hand panel for one clicked change area (Task B3), laid out as in docs/mockups/app-mockup.html.
import { FIXTURE_MESSAGE } from "../api.ts";
import { AGREEMENT_COLORS, type Agreement, type ChangeArea, type ConfidenceLabel, type Evidence, type Result } from "../types.ts";
import {
  AGREEMENT_TEXT,
  classTitle,
  formatHa,
  formatNumber,
  formatP,
  longDate,
  ordinal,
  toTime,
  withUnit,
} from "./changeFormat.ts";
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

const CHIP_BG: Record<Agreement, string> = { L: "#3a2a08", both: "#271d45", C: "#0b2c33" };
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
  const anyExport = EXPORTS.some((e) => result.exports[e.key]);

  return (
    <section className="cp" aria-label={`Change area: ${title}`}>
      <div className="cp-chips">
        <span className="cp-chip" style={{ background: CHIP_BG[area.agreement], color: AGREEMENT_COLORS[area.agreement] }}>
          {AGREEMENT_TEXT[area.agreement]}
        </span>
        {result.fixture && (
          <span className="cp-example" title={FIXTURE_MESSAGE}>
            Example data
          </span>
        )}
        {onClose && (
          <button type="button" className="cp-close" aria-label="Close" onClick={onClose}>
            ×
          </button>
        )}
      </div>
      <h2 className="cp-title">{title}</h2>

      <div className="cp-conf">
        <span>Confidence</span>
        <div className="cp-bar" aria-hidden="true">
          <i style={{ width: `${confidence * 100}%`, background: CONF_COLOR[area.confidence_label] ?? "var(--muted)" }} />
        </div>
        <span>
          <b>{area.confidence_label}</b> · {formatP(area.p_value)} · {formatHa(area.area_ha)} ha
        </span>
      </div>
      {Number.isFinite(changeT) && <p className="cp-when">First seen changed on the {longDate(changeT)} pass.</p>}

      {area.plain_text && (
        <div className="cp-plain">
          {area.plain_text}
          <small>A plain-language summary of the evidence below. AI may reword it; it can't change the verdict.</small>
        </div>
      )}

      {area.evidence.length > 0 && (
        <>
          <div className="cp-label">Why we think so</div>
          <ul className="cp-ev" aria-label="Evidence">
            {area.evidence.map((ev, i) => (
              <EvidenceItem key={`${ev.label}-${i}`} ev={ev} />
            ))}
          </ul>
        </>
      )}

      <div className="cp-label">Every pass, averaged over this area</div>
      <SeriesChart series={area.series} changeDate={area.change_date} />

      <People tracts={result.people.svi_tracts} />

      <div className="cp-label">Take it with you</div>
      <div className="cp-exports">
        {EXPORTS.map((e) => {
          const url = result.exports[e.key];
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
      {!anyExport && <p className="cp-note">Exports come with live analyses: draw a box to get them.</p>}
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
      <div className="cp-label">Who lives here</div>
      <div className="cp-who">
        <p>Census tracts in this box, ranked by social vulnerability (CDC SVI 2022; higher = harder to recover from disasters).</p>
        <ul aria-label="Census tracts">
          {ranked.slice(0, MAX_TRACTS).map((t) => (
            <li key={t.geoid}>
              <span>{t.name}</span>
              <b>{ordinal(Math.round(t.rpl_themes * 100))} percentile</b>
            </li>
          ))}
        </ul>
        {more > 0 && <small>{`+${more} more ${more === 1 ? "tract" : "tracts"} in this box`}</small>}
      </div>
    </>
  );
}

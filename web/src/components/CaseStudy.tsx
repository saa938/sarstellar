import type { Result } from "../types.ts";
import "./CaseStudy.css";

export interface CaseStudyProps {
  storyId: string | null;
  result: Result | null;
  onSelectArea?: (id: string) => void;
}

const PERIMETER_URL = "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters_YearToDate/FeatureServer/0/query?where=attr_UniqueFireIdentifier%3D%272026-WACOA-260140%27&outFields=poly_IncidentName%2Cattr_FireDiscoveryDateTime%2Cpoly_DateCurrent%2Cattr_UniqueFireIdentifier&returnGeometry=false&f=json";

function bandValue(result: Result, id: string, band: string): string {
  const value = result.areas.find((area) => area.id === id)?.evidence.find((ev) => ev.label === `${band} change`)?.value;
  return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(2).replace("-", "−")} dB` : "Not recorded";
}

/** A walkthrough of the saved result, with corroboration kept separate from radar observations. */
export default function CaseStudy({ storyId, result, onSelectArea }: CaseStudyProps) {
  if (storyId !== "kaiser" || !result) return null;
  const area = result.areas.find((candidate) => candidate.id === "a1");
  if (!area) return null;
  const hasPerimeter = area.evidence.some((ev) => ev.label === "Inside fire perimeter" && ev.value === "yes");
  return (
    <details className="case-study">
      <summary>Investigation: Kaiser Canyon</summary>
      <h3>What changed inside the mapped fire perimeter?</h3>
      <p>Compare July 13–September 11, 2026. Inspect area {area.id}, a {area.area_ha.toLocaleString("en-US")} ha patch first flagged on July 25.</p>
      <dl>
        <div><dt>Observed NISAR HV change</dt><dd>{bandValue(result, area.id, "HV")}</dd></div>
        <div><dt>Observed Sentinel-1 VH change</dt><dd>{bandValue(result, area.id, "VH")}</dd></div>
      </dl>
      <p><b>Why the disagreement?</b> This patch has the NISAR-majority label: NISAR flagged a majority of its blocks; Sentinel-1 did not. That does not imply zero Sentinel-1 detections. Both radars share the endpoint dates, but NISAR has {result.nisar.dates.length} acquisitions versus {result.s1?.dates.length ?? 0}; its extra dates could affect the result.</p>
      <p><b>Corroboration:</b> {hasPerimeter ? "The saved result records overlap with a NIFC fire perimeter. " : "The saved result has no fire-perimeter corroboration. "}
        <a href={PERIMETER_URL} target="_blank" rel="noreferrer">NIFC's Kaiser Canyon record</a> gives a July 16 discovery date. The perimeter was updated October 20; it supports fire context, not the exact date or cause of every changed block.</p>
      <p><b>Still unresolved:</b> The cause remains a possible burn. Perimeter overlap helped the rule assign that hypothesis, so it is not a separate validation test. No verified optical inspection or field survey is attached.</p>
      <div className="case-study-actions">
        {onSelectArea && <button type="button" onClick={() => onSelectArea(area.id)}>Inspect area {area.id}</button>}
        {onSelectArea && result.areas.some((candidate) => candidate.id === "a3") && <button type="button" onClick={() => onSelectArea("a3")}>Compare area a3</button>}
        <a href="/stories/kaiser/areas.csv" download>Download saved areas (CSV)</a>
      </div>
      <p className="case-study-result"><b>More radar did not guarantee better detection.</b> In the controlled forest-loss test, fusion lowered AUPRC by 0.073 (95% interval −0.157 to −0.009). We selected methods on training states, then tested one pair per radar on held-out states. <a href="#/scorecard">See the benchmark</a>.</p>
    </details>
  );
}

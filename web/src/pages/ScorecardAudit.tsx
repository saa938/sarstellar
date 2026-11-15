import type { Scorecard } from "../types.ts";
import { eligibleSites, holdoutSummary } from "./scorecardModel.ts";

/** Counts and caveats stay tied to the published report, including unsuccessful sites. */
export default function ScorecardAudit({ sc }: { sc: Scorecard }) {
  const sites = eligibleSites(sc);
  const held = holdoutSummary(sc);
  const attempted = sc.n_attempted ?? sc.attempted_sites?.length ?? sc.sites.length;
  const failed = sc.failed_sites?.length ?? 0;
  const excluded = sc.excluded_sites?.length ?? 0;
  const floods = sites.filter((s) => s.kind === "flood" && s.split === "holdout");
  return (
    <section className="pg-card">
      <h2>Evaluation sample</h2>
      <dl className="pg-sample-counts" aria-label="Evaluation counts">
        <div><dt>Attempted</dt><dd>{attempted}</dd></div>
        {sc.n_processed_sites !== undefined && <div><dt>Processed</dt><dd>{sc.n_processed_sites}</dd></div>}
        <div><dt>Eligible</dt><dd>{sc.n_comparable_sites ?? sc.n_sites}</dd></div>
        <div><dt>Training</dt><dd>{sc.n_train_sites ?? sites.filter((s) => s.split === "train").length}</dd></div>
        <div><dt>Held out</dt><dd>{held.nSites}</dd></div>
        <div><dt>Failed</dt><dd>{failed}</dd></div>
        <div><dt>Excluded</dt><dd>{excluded}</dd></div>
      </dl>
      <p className="pg-note">
        Eligibility requires common valid NISAR, Sentinel-1, coarser NISAR and reference blocks.
        {sc.status === "incomplete" && " This report is incomplete."}
      </p>
      <ul className="pg-note pg-list">
        {floods.length > 0 && <li>{floods.length} held-out flood {floods.length === 1 ? "site" : "sites"}, plus stable controls. Flood uncertainty is limited by this small sample.</li>}
        <li>DSWx-S1 uses Sentinel-1; the flood reference is not sensor-independent.</li>
        <li>CDL marks cultivated land, not confirmed crop change.</li>
        <li>Reference-selected events and controls: no estimate of national prevalence or multiclass cause-label accuracy.</li>
      </ul>
      {sc.bootstrap && <p className="pg-meta">
        {sc.bootstrap.n_draws} whole-site bootstrap draws · {sc.bootstrap.confidence * 100}% intervals
      </p>}
      {sc.notes && <details><summary>Reference data and interpretation</summary><p>{sc.notes}</p></details>}
    </section>
  );
}

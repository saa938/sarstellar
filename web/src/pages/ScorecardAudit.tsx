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
      <h2>What was actually evaluated</h2>
      <p>
        {sc.n_comparable_sites ?? sc.n_sites} eligible sites from {attempted} attempted.
        {sc.n_processed_sites !== undefined && ` ${sc.n_processed_sites} sites were processed;`}
        {` ${failed} failed and ${excluded} were excluded from comparison.`}
        {` ${held.nSites} held-out sites in ${held.states.length} states; `}
        {sc.n_train_sites ?? sites.filter((s) => s.split === "train").length} training sites.
      </p>
      <p className="pg-note">
        Every primary detector is measured on the same blocks with valid paired NISAR, Sentinel-1, coarser NISAR
        and reference data. Sites were selected around reference events and controls; these scores do not estimate
        national change prevalence or measure multiclass cause-label accuracy.
        {floods.length > 0 && ` Flood results have only ${floods.length} held-out flood ${floods.length === 1 ? "site" : "sites"}, plus stable controls; interpret their uncertainty cautiously.`}
        {sc.status === "incomplete" && " This report is incomplete."}
      </p>
      {sc.bootstrap && <p className="pg-meta">
        {sc.bootstrap.n_draws} whole-site bootstrap draws · {sc.bootstrap.confidence * 100}% intervals
      </p>}
      {sc.notes && <details><summary>Reference data and interpretation</summary><p>{sc.notes}</p></details>}
    </section>
  );
}

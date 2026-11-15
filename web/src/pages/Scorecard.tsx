// Scorecard page (Task B6): the national two-radar result from /scorecard.json (written by Task C2).
// Headline = the held-out fusion test; every number on the page comes from that file.
import { useEffect, useState } from "react";
import { loadScorecard } from "../api.ts";
import type { Detector, Scorecard, ScorecardClassRow } from "../types.ts";
import "./pages.css";
import SiteMap, { SPLIT_COLORS } from "./SiteMap.tsx";
import ScorecardAudit from "./ScorecardAudit.tsx";
import {
  BAR_METRIC,
  BAR_METRIC_LABEL,
  DETECTORS,
  clamp01,
  classLabel,
  classTitle,
  detectorInfo,
  eligibleSites,
  fmt,
  fusionHeadline,
  groupClasses,
  holdoutSummary,
  isNum,
  pct,
  ratio,
  signed,
} from "./scorecardModel.ts";

/** Loads /scorecard.json: undefined while loading, null when the file doesn't exist yet. */
export function useScorecard(enabled = true): Scorecard | null | undefined {
  const [sc, setSc] = useState<Scorecard | null | undefined>(undefined);
  useEffect(() => {
    if (!enabled) return;
    let live = true;
    loadScorecard().then(
      (d) => live && setSc(d),
      () => live && setSc(null),
    );
    return () => {
      live = false;
    };
  }, [enabled]);
  return sc;
}

export interface ScorecardPageProps {
  /** Scorecard to show. Omit to load /scorecard.json here; null renders nothing (no scorecard yet). */
  data?: Scorecard | null;
}

/** Renders nothing until a scorecard exists, so the page stays hidden before Task C2 publishes. */
export default function ScorecardPage({ data }: ScorecardPageProps) {
  const loaded = useScorecard(data === undefined);
  const sc = data === undefined ? loaded : data;
  return sc ? <ScorecardView sc={sc} /> : null;
}

function ScorecardView({ sc }: { sc: Scorecard }) {
  const headline = fusionHeadline(sc);
  const op = sc.operating_point;
  return (
    <main className="pg">
      <div className="pg-inner">
        <div className="pg-kicker">National scorecard · held-out test</div>
        <section className={`pg-card pg-headline pg-${headline.kind}`}>
          <h1>{headline.text}</h1>
          {headline.detail && <p className="pg-detail">{headline.detail}</p>}
          <p className="pg-meta">
            {sc.n_sites} sites scored · generated {formatDate(sc.generated_at)}
            {op && ` · default setting: false discovery rate q = ${op.q}, change of at least ${op.min_db} dB`}
          </p>
        </section>
        <FusionTable sc={sc} />
        <ScorecardAudit sc={sc} />
        <HowToRead />
        {!!sc.learned_fusion?.length && <FusionTable sc={{ ...sc, fusion: sc.learned_fusion }} learned />}
        <ClassBars rows={sc.classes ?? []} />
        <EqualRecall sc={sc} />
        <StableFalseAlarms fa={sc.stable_fa} />
        <Sites sc={sc} />
        {sc.model && <ModelTable model={sc.model} />}
      </div>
    </main>
  );
}

function HowToRead() {
  return (
    <details className="pg-card pg-howto">
      <summary>How to read this</summary>
      <ul>
        <li>
          Each site is a box about 10 km on a side with a reference map: optical vegetation-loss alerts
          (OPERA DIST-ALERT-HLS), fire perimeters (NIFC), surface-water maps (OPERA DSWx) or crop maps (USDA CDL). These
          references are products, not field surveys. DSWx-S1 itself uses Sentinel-1, so flood labels are not
          sensor-independent. CDL marks cultivated land, not a confirmed crop change.
        </li>
        <li>
          Scores are per 1-hectare block. <b>Precision</b>: of the blocks a radar flagged, the share the reference agrees
          with. <b>Recall</b>: of the reference blocks, the share the radar flagged. <b>AUPRC</b> (area under the
          precision–recall curve, 0 to 1, higher is better) sums up every threshold, not just the default one.
        </li>
        <li>
          States are split into training and held-out. Thresholds and the logistic fusion were fit on training states
          only; the comparisons here are measured on held-out states the models never saw.
        </li>
        <li>
          Thin lines on the bars are 95% confidence intervals from resampling whole sites. The paired interval in the
          fusion table tests the difference directly; overlapping individual bars are not that test.
        </li>
        <li>
          <b>NISAR at 30 m</b> samples NISAR on a coarser pixel lattice before block averaging. This checks sensitivity
          to sampling; it does not isolate wavelength from timing, geometry, processing or other sensor differences.
        </li>
      </ul>
    </details>
  );
}

function FusionTable({ sc, learned = false }: { sc: Scorecard; learned?: boolean }) {
  const rows = sc.fusion ?? [];
  if (rows.length === 0) return null;
  return (
    <section className="pg-card">
      <h2>{learned ? "Learned fusion with matched training" : "Does combining both radars help?"}</h2>
      <p className="pg-note">
        Change in {BAR_METRIC_LABEL} when NISAR and Sentinel-1 are combined, compared with the better single radar for
        each change type, on held-out states. Methods are selected on training states before evaluation.
        {learned ? " These models all receive the same training labels; gains cannot be attributed to extra supervision alone."
          : " The primary comparison uses Fisher or Bonferroni fusion; learned models are shown separately."}
      </p>
      <div className="pg-scroll">
        <table className="pg-table">
          <thead>
            <tr>
              <th scope="col">Change type</th>
              <th scope="col">Better single radar</th>
              <th scope="col">Combined with</th>
              <th scope="col">Change in {BAR_METRIC_LABEL}</th>
              <th scope="col">95% CI</th>
              <th scope="col">Resamples with a gain</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const tone = r.ci_low > 0 ? "pg-up" : r.ci_high < 0 ? "pg-down" : "";
              return (
                <tr key={`${r.class}-${r.fused}`}>
                  <td>{classTitle(r.class)}</td>
                  <td>{detectorInfo(r.best_single).label}</td>
                  <td>{fusionMethod(r.fused)}</td>
                  <td className={`pg-n ${tone}`}>{signed(r.delta)}</td>
                  <td className="pg-n">
                    {fmt(r.ci_low)} to {fmt(r.ci_high)}
                  </td>
                  <td className="pg-n">{pct(r.p_gt0)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function fusionMethod(d: Detector): string {
  return d === "fused_fisher" ? "Fisher fusion" : d === "fused_logistic" ? "Logistic fusion" : detectorInfo(d).label;
}

function ClassBars({ rows }: { rows: ScorecardClassRow[] }) {
  const [landcover, setLandcover] = useState("all");
  const pooled = rows.some((row) => row.landcover === "all");
  const covers = [...new Set(rows.map((row) => row.landcover))].filter((cover) => cover !== "all").sort();
  const groups = groupClasses(landcover === "all" && !pooled ? rows : rows.filter((row) => row.landcover === landcover));
  if (groups.length === 0) return null;
  return (
    <section className="pg-card">
      <h2>Detection quality by change type</h2>
      {covers.length > 0 && <label className="pg-filter">Land cover
        <select value={landcover} onChange={(event) => setLandcover(event.target.value)}>
          <option value="all">{pooled ? "All land covers (pooled)" : "All available land covers"}</option>
          {covers.map((cover) => <option key={cover} value={cover}>{cover.replace(/_/g, " ")}</option>)}
        </select>
      </label>}
      <p className="pg-note">
        {BAR_METRIC_LABEL} per radar on held-out states, with 95% intervals.{" "}
        <Swatch color={detectorInfo("L").color} /> NISAR, <Swatch color={detectorInfo("C").color} /> Sentinel-1,{" "}
        <Swatch color={detectorInfo("fused_fisher").color} /> both combined; lighter bars are variants.
      </p>
      <div className="pg-grid">
        {groups.map((g) => (
          <article key={g.key} className="pg-class">
            <h3>
              {classTitle(g.cls)} <span className="pg-lc">· {g.landcover}</span>
            </h3>
            <div className="pg-meta">{g.nRef.toLocaleString("en-US")} reference blocks</div>
            {g.rows.map((r) => (
              <MetricBar key={r.detector} row={r} />
            ))}
            <details>
              <summary>At the default setting</summary>
              <table className="pg-table pg-small">
                <thead>
                  <tr>
                    <th scope="col">Radar</th>
                    <th scope="col">Precision</th>
                    <th scope="col">Recall</th>
                    <th scope="col">F1</th>
                    <th scope="col">Blocks flagged</th>
                  </tr>
                </thead>
                <tbody>
                  {g.rows.map((r) => (
                    <tr key={r.detector}>
                      <td>{detectorInfo(r.detector).label}</td>
                      <td className="pg-n">{fmt(r.precision)}</td>
                      <td className="pg-n">{fmt(r.recall)}</td>
                      <td className="pg-n">{fmt(r.f1)}</td>
                      <td className="pg-n">{isNum(r.n_flags) ? r.n_flags.toLocaleString("en-US") : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          </article>
        ))}
      </div>
    </section>
  );
}

function MetricBar({ row }: { row: ScorecardClassRow }) {
  const info = detectorInfo(row.detector);
  const v = row[BAR_METRIC];
  const { ci_low: lo, ci_high: hi } = row;
  const hasCi = isNum(lo) && isNum(hi);
  const label = `${info.label}: ${BAR_METRIC_LABEL} ${fmt(v)}${hasCi ? `, 95% CI ${fmt(lo)} to ${fmt(hi)}` : ""}`;
  const opacity = info.dim ? 0.55 : 1;
  return (
    <div className="pg-bar">
      <span className="pg-bar-name">
        <Swatch color={info.color} opacity={opacity} />
        {info.label}
      </span>
      <div className="pg-track" role="img" aria-label={label}>
        {isNum(v) && <div className="pg-fill" style={{ width: `${clamp01(v) * 100}%`, background: info.color, opacity }} />}
        {hasCi && <div className="pg-ci" style={{ left: `${clamp01(lo) * 100}%`, width: `${(clamp01(hi) - clamp01(lo)) * 100}%` }} />}
      </div>
      <span className="pg-bar-num">
        {fmt(v)}
        {hasCi && (
          <small>
            {" "}
            {fmt(lo)}–{fmt(hi)}
          </small>
        )}
      </span>
    </div>
  );
}

function EqualRecall({ sc }: { sc: Scorecard }) {
  const rows = sc.equal_recall ?? [];
  if (rows.length === 0) return null;
  return (
    <section className="pg-card">
      <h2>Precision at equal recall</h2>
      <p className="pg-note">
        When both radars find the same share of the reference change, how often is each one right? A ratio above 1 means
        NISAR is more precise; below 1, Sentinel-1 is.
      </p>
      <div className="pg-scroll">
        <table className="pg-table">
          <thead>
            <tr>
              <th scope="col">Change type</th>
              <th scope="col">At recall</th>
              <th scope="col">NISAR</th>
              <th scope="col">NISAR at 30 m</th>
              <th scope="col">Sentinel-1</th>
              <th scope="col">NISAR ÷ Sentinel-1</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.class}>
                <td>{classTitle(r.class)}</td>
                <td className="pg-n">{pct(r.recall, 0)}</td>
                <td className="pg-n">{pct(r.precision_L, 0)}</td>
                <td className="pg-n">{pct(r.precision_L30, 0)}</td>
                <td className="pg-n">{pct(r.precision_C, 0)}</td>
                <td className={`pg-n pg-ratio ${isNum(r.ratio_L_over_C) ? (r.ratio_L_over_C >= 1 ? "pg-l" : "pg-c") : ""}`}>
                  {ratio(r.ratio_L_over_C)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function StableFalseAlarms({ fa }: { fa: Scorecard["stable_fa"] | undefined }) {
  const rows = DETECTORS.flatMap((d) => isNum(fa?.[d]) ? [{ d, v: fa![d] as number }] : []);
  if (rows.length === 0) return null;
  const scale = Math.max(0.02, ...rows.map((r) => r.v));
  return (
    <section className="pg-card">
      <h2>False alarms on stable ground</h2>
      <p className="pg-note">
        Share of 1-hectare blocks flagged at held-out stable control sites, at each detector's operating point.
        The benchmark target is at most 1.5%; rates above it remain visible. A 5% FDR setting does not guarantee a
        1.5% stable-ground false-alarm rate. Logistic fusion uses a threshold calibrated on training controls.
      </p>
      {rows.map(({ d, v }) => {
        const info = detectorInfo(d);
        const opacity = info.dim ? 0.55 : 1;
        return (
          <div className="pg-bar" key={d}>
            <span className="pg-bar-name">
              <Swatch color={info.color} opacity={opacity} />
              {info.label}
            </span>
            <div className="pg-track" aria-hidden="true">
              <div className="pg-fill" style={{ width: `${(v / scale) * 100}%`, background: info.color, opacity }} />
            </div>
            <span className="pg-bar-num">{pct(v)}</span>
          </div>
        );
      })}
    </section>
  );
}

function Sites({ sc }: { sc: Scorecard }) {
  const sites = eligibleSites(sc);
  if (sites.length === 0) return null;
  const { nSites: nHeld, states } = holdoutSummary(sc);
  const nTrain = sites.length - nHeld;
  const kinds = new Map<string, number>();
  for (const s of sites) kinds.set(s.kind, (kinds.get(s.kind) ?? 0) + 1);
  return (
    <section className="pg-card">
      <h2>Where the sites are</h2>
      <div className="pg-legend">
        <span>
          <Swatch color={SPLIT_COLORS.train} round />
          {nTrain} training {nTrain === 1 ? "site" : "sites"}
        </span>
        <span>
          <Swatch color={SPLIT_COLORS.holdout} round />
          {nHeld} held-out {nHeld === 1 ? "site" : "sites"} in {[...states].sort().join(", ")}
        </span>
      </div>
      <SiteMap sites={sites} />
      <p className="pg-note">
        By kind:{" "}
        {[...kinds]
          .map(([k, n]) => `${classLabel(k)} ${n}`)
          .join(" · ")}
        . Each dot is the center of a site box.
      </p>
    </section>
  );
}

function ModelTable({ model }: { model: NonNullable<Scorecard["model"]> }) {
  return (
    <section className="pg-card">
      <h2>Rules vs learned model</h2>
      <p className="pg-note">
        F1 on held-out states for the physics rules and a learned cause model. The app uses the model only for change
        types where it wins.
      </p>
      <div className="pg-scroll">
        <table className="pg-table">
          <thead>
            <tr>
              <th scope="col">Change type</th>
              <th scope="col">Rules F1</th>
              <th scope="col">Model F1</th>
              <th scope="col">Used in the app</th>
            </tr>
          </thead>
          <tbody>
            {(model.per_class ?? []).map((r) => (
              <tr key={r.class}>
                <td>{classTitle(r.class)}</td>
                <td className="pg-n">{fmt(r.rules_f1)}</td>
                <td className="pg-n">{fmt(r.model_f1)}</td>
                <td>{r.winner === "model" ? "Learned model" : r.winner === "rules" ? "Rules" : r.winner}</td>
              </tr>
            ))}
            <tr className="pg-total">
              <td>Average over types (macro F1)</td>
              <td className="pg-n">{fmt(model.macro_f1_rules)}</td>
              <td className="pg-n">{fmt(model.macro_f1_model)}</td>
              <td />
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Swatch({ color, opacity = 1, round = false }: { color: string; opacity?: number; round?: boolean }) {
  return <i className={`pg-sw${round ? " pg-round" : ""}`} style={{ background: color, opacity }} aria-hidden="true" />;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" })} UTC`;
}

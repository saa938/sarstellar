import { useEffect, useState } from "react";
import { Nav } from "../components/Nav";
import { Footer } from "../components/Footer";
import { loadProof } from "../lib/data";
import { DATA_CREDITS, REPO_URL } from "../lib/credits";
import { CHANGE_LABEL, DB_NOTE } from "../lib/labels";
import { fmtInt } from "../lib/format";

type R = Record<string, unknown>;
type N = number | null | undefined;

const num = (v: N, d = 2) => (v == null ? "not measured" : v < 0.01 && v > 0 ? v.toFixed(4) : v.toFixed(d));
const pct = (v: N) => (v == null ? "not measured" : `${(v * 100).toFixed(v < 0.1 ? 1 : 0)}%`);
const ci = (c: unknown) => (Array.isArray(c) && c.length === 2 ? ` (${num(c[0] as number)} to ${num(c[1] as number)})` : "");

export default function Method() {
  const [p, setP] = useState<R | null | undefined>(undefined);
  useEffect(() => {
    loadProof().then(setP);
  }, []);
  const h = (p?.headline ?? {}) as Record<string, N>;
  const moves = (p?.moves ?? []) as R[];
  const pol = p?.polarization as { classes: string[]; variants: { name: string; auprc: Record<string, N>; auprc_ci?: Record<string, [number, number]> }[] } | undefined;
  const s1 = p?.sentinel1 as R | undefined;
  const cc = (p?.cross_continent ?? []) as R[];
  const any = p?.any_move as { precision?: N; recall?: N; base_rate?: N } | undefined;
  const limits = (p?.limits ?? []) as string[];
  return (
    <div className="page">
      <Nav active="method" />
      <header className="page__head">
        <div className="eyebrow">Method</div>
        <h1 className="sec__title">How SARstellar works, and how well</h1>
        <p className="sec__lede" style={{ maxWidth: 760 }}>
          From NASA's archive to a measured answer, in five steps. Every number on this site comes from this pipeline, and the code is open.
        </p>
      </header>
      <div className="page__body">
        <ol className="steps">
          <li>
            <strong>Data.</strong> NISAR Level-2 GCOV images, radar backscatter in HH and HV, from NASA's Alaska Satellite Facility archive. NISAR is a
            joint NASA-ISRO mission and images nearly all land every 12 days, day or night, through cloud.
          </li>
          <li>
            <strong>Passes.</strong> For each place we take every pass from the same orbit track and mode, so the radar looks the same way each time and
            only the ground changes.
          </li>
          <li>
            <strong>Hectares.</strong> Each image is averaged into 100 m squares, one hectare each, in decibels ({DB_NOTE}). Each hectare becomes a dot
            placed by its HH and HV.
          </li>
          <li>
            <strong>Model.</strong> A gradient-boosted tree model (LightGBM) learns how much HH and HV change, between two passes, for each kind of change.
            It learns from {h.train_sites ?? "the training"} US places where independent maps say what happened: optical forest-loss alerts, fire
            perimeters, water maps and cropland maps.
          </li>
          <li>
            <strong>Held-out test.</strong> It is scored on {h.test_sites ?? "held-out"} places in {h.test_states ?? "several"} states it never saw, and
            on a place in Brazil. Intervals resample whole places, so they show how much results vary from place to place.
          </li>
        </ol>

        {p && (
          <section className="msec">
            <h2 className="msec__title">The numbers</h2>
            <p className="msec__p">
              Two measures, explained once. <b>AUPRC</b> scores how well the model ranks the hectares that really changed above those that did not; a
              random guess scores the share of hectares that really changed (the base rate), so the ratio between them is the skill.{" "}
              <b>Precision</b> is how often a hectare the map labels is really that change; <b>recall</b> is how much of the real change the map finds.
              Maps only name a change where HV moved at least 2.5 dB or HH 3 dB.
            </p>
            <div className="tablewrap">
              <table className="mtable">
                <thead>
                  <tr>
                    <th>Change</th>
                    <th>Checked against</th>
                    <th>AUPRC (95% interval)</th>
                    <th>Random guess</th>
                    <th>Times better</th>
                    <th>Precision</th>
                    <th>Recall</th>
                  </tr>
                </thead>
                <tbody>
                  {moves.map((m) => {
                    const a = m.auprc as N;
                    const b = m.base_rate as N;
                    const c = m.auprc_ci as [number, number] | undefined;
                    const chance = c && b != null && c[0] <= b;
                    return (
                      <tr key={String(m.id)}>
                        <td>{CHANGE_LABEL[String(m.id)] ?? String(m.name)}</td>
                        <td className="dim">{String(m.reference ?? "")}</td>
                        <td className="num">
                          {num(a)}
                          <span className="dim">{ci(c)}</span>
                        </td>
                        <td className="num">{num(b, 3)}</td>
                        <td className="num">{a != null && b ? `${(a / b).toFixed(a / b >= 10 ? 0 : 1)}×${chance ? " (not distinguishable from chance)" : ""}` : "?"}</td>
                        <td className="num">{pct(m.precision as N)}</td>
                        <td className="num">{pct(m.recall as N)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <ul className="mfacts">
              {any?.precision != null && (
                <li>
                  <b>Any change at all:</b> when a map names a change, it is real {pct(any.precision)} of the time; {pct(any.base_rate)} of hectares really
                  changed; the maps find {pct(any.recall)} of them.
                </li>
              )}
              {s1 && (
                <li>
                  <b>NISAR against Sentinel-1 (forest loss, {String(s1.n_sites ?? "")} sites):</b> at {pct(s1.recall as N)} recall, {pct(s1.precision_nisar as N)} of
                  NISAR alerts were real against {pct(s1.precision_s1 as N)} for Sentinel-1 ({String(s1.ratio ?? "")}×). AUPRC {num(s1.auprc_nisar as N, 3)}
                  {ci(s1.auprc_nisar_ci)} against {num(s1.auprc_s1 as N, 3)}
                  {ci(s1.auprc_s1_ci)}.
                </li>
              )}
              {cc.map((c) => (
                <li key={String(c.stage)}>
                  <b>
                    {c.stage === "rondonia" ? "Rondonia, Brazil (never trained on)" : c.stage === "morton" ? "Morton, Washington (in a training state, not held out)" : String(c.stage)}:
                  </b>{" "}
                  forest loss AUPRC {num(c.auprc as N, 3)} against a random guess of {num(c.base_rate as N, 4)}; precision {pct(c.precision as N)}, recall{" "}
                  {pct(c.recall as N)}, {c.n_positive != null ? `${fmtInt(c.n_positive as number)} reference hectares of ${fmtInt(c.n_blocks as number)}` : ""}.
                </li>
              ))}
            </ul>
            {pol && (
              <>
                <h3 className="msec__sub">Which channel carries each change</h3>
                <p className="msec__p">The same model retrained with HH only, HV only, and both (AUPRC on the held-out states).</p>
                <div className="tablewrap">
                  <table className="mtable mtable--pol">
                    <thead>
                      <tr>
                        <th>Change</th>
                        {pol.variants.map((v) => (
                          <th key={v.name}>{v.name}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {pol.classes.map((c) => (
                        <tr key={c}>
                          <td>{CHANGE_LABEL[c] ?? c}</td>
                          {pol.variants.map((v) => (
                            <td key={v.name} className="num">
                              {num(v.auprc?.[c] as N, 3)}
                              <span className="dim">{ci(v.auprc_ci?.[c])}</span>
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
            <p className="msec__p dim">
              {h.reference_sites != null && `${fmtInt(h.reference_sites)} reference places · `}
              {h.hectares_scored != null && `${fmtInt(h.hectares_scored)} hectares scored · `}
              {h.passes_read != null && `${fmtInt(h.passes_read)} NISAR granules read · `}
              {h.stages != null && `${h.stages} places on this site in ${h.countries ?? "?"} countries`}
            </p>
          </section>
        )}

        {limits.length > 0 && (
          <section className="msec">
            <h2 className="msec__title">Limits</h2>
            <ul className="mlimits">
              {limits.map((l, i) => (
                <li key={i}>{l}</li>
              ))}
            </ul>
          </section>
        )}

        <section className="msec">
          <h2 className="msec__title">Data and credits</h2>
          <div className="credits2">
            {DATA_CREDITS.map((c) => (
              <a key={c.name} href={c.url} target="_blank" rel="noreferrer">
                <strong>{c.name}</strong>
                <span>{c.role}</span>
              </a>
            ))}
          </div>
        </section>

        <section className="msec">
          <h2 className="msec__title">Code and AI use</h2>
          <p className="msec__p">
            The pipeline, the model, the evaluation and this site are open source under the Apache-2.0 license:{" "}
            <a href={REPO_URL} target="_blank" rel="noreferrer">
              {REPO_URL.replace("https://", "")}
            </a>
            .
          </p>
          <p className="msec__p">AI coding assistants helped write code and text.</p>
          <p className="msec__p dim">
            Built for the NASA Space Apps Challenge 2026, "Dancing with the SARs". NISAR is a joint mission of NASA and ISRO; this project is independent and
            not endorsed by either agency.
          </p>
        </section>
      </div>
      <Footer />
    </div>
  );
}

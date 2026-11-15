import { useEffect, useState } from "react";
import { Nav } from "../components/Nav";
import { Footer } from "../components/Footer";
import { loadProof } from "../lib/data";
import { MOVE_COLORS, MOVE_NAMES, POL_COLORS } from "../lib/moves";
import { fmtInt } from "../lib/format";
import { ProofTeaser } from "./Landing";

type R = Record<string, unknown>;
type N = number | null | undefined;

export function CI({ lo, hi }: { lo: N; hi: N }) {
  if (lo == null || hi == null) return null;
  return (
    <span className="ci">
      [{lo.toFixed(2)}, {hi.toFixed(2)}]
    </span>
  );
}

interface Row {
  label: string;
  value: N;
  lo?: N;
  hi?: N;
  color?: string;
  base?: N;
  note?: string;
}

/** Dot-and-interval rows on one shared 0..max axis. */
function IntervalChart({ rows, max = 1, unit = "AUPRC", baseLabel = "random guess (base rate)" }: { rows: Row[]; max?: number; unit?: string; baseLabel?: string }) {
  const W = 640;
  const rowH = 34;
  const ml = 150;
  const mr = 70;
  const H = rows.length * rowH + 34;
  const X = (v: number) => ml + (Math.min(Math.max(v, 0), max) / max) * (W - ml - mr);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);
  const anyBase = rows.some((r) => r.base != null);
  return (
    <figure className="ichart">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={`${unit} with 95% intervals`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={X(t)} x2={X(t)} y1={6} y2={H - 26} className="chart__grid" />
            <text x={X(t)} y={H - 10} textAnchor="middle" className="chart__tick">
              {t.toFixed(2)}
            </text>
          </g>
        ))}
        {rows.map((r, i) => {
          const y = 14 + i * rowH + rowH / 2 - 8;
          const has = r.value != null;
          return (
            <g key={r.label + i}>
              <text x={ml - 12} y={y + 4} textAnchor="end" className="ichart__label">
                {r.label}
              </text>
              {r.base != null && <line x1={X(r.base)} x2={X(r.base)} y1={y - 9} y2={y + 9} className="ichart__base" />}
              {has && r.lo != null && r.hi != null && <line x1={X(r.lo)} x2={X(r.hi)} y1={y} y2={y} className="ichart__ci" style={{ stroke: r.color }} />}
              {has ? (
                <circle cx={X(r.value!)} cy={y} r={5.5} fill={r.color ?? "#efede6"} stroke="#06070b" strokeWidth={2}>
                  <title>{`${r.label}: ${r.value!.toFixed(3)}${r.lo != null ? ` (95% interval ${r.lo!.toFixed(2)} to ${r.hi!.toFixed(2)})` : ""}`}</title>
                </circle>
              ) : (
                <text x={ml + 4} y={y + 4} className="ichart__nm">
                  not measured
                </text>
              )}
              {has && (
                <text x={W - mr + 10} y={y + 4} className="ichart__val">
                  {r.value!.toFixed(2)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <figcaption>
        {unit}, dots with 95% site-bootstrap intervals.{anyBase ? ` Thin ticks mark a ${baseLabel}.` : ""}
      </figcaption>
    </figure>
  );
}

export default function Proof() {
  const [proof, setProof] = useState<R | null | undefined>(undefined);
  useEffect(() => {
    loadProof().then(setProof);
  }, []);
  return (
    <div className="page">
      <Nav active="proof" />
      <header className="page__head">
        <div className="eyebrow">How we know</div>
        <h1 className="act__title">The evidence</h1>
        <p className="act__lede" style={{ maxWidth: 760 }}>
          Every number on this site comes from the pipeline, measured on places the model never saw, with a 95% interval from resampling whole sites.
          When something was not measured, it says so.
        </p>
        {proof && (proof.fixture as boolean) && <p className="dim">This proof file is marked as a fixture.</p>}
      </header>
      <div className="page__body">{proof === undefined ? null : proof ? <ProofBody p={proof} /> : <ProofTeaser proof={null} />}</div>
      <Footer />
    </div>
  );
}

function ProofBody({ p }: { p: R }) {
  const h = (p.headline ?? {}) as Record<string, N>;
  const moves = (p.moves ?? []) as R[];
  const pol = p.polarization as { classes: string[]; variants: { name: string; auprc: Record<string, N>; auprc_ci?: Record<string, [number, number]> }[] } | undefined;
  const s1 = p.sentinel1 as R | undefined;
  const cc = (p.cross_continent ?? []) as R[];
  const conf = p.confusion as { classes: string[]; rows_true_cols_pred: number[][] } | undefined;
  const limits = (p.limits ?? []) as string[];
  const macro = p.macro_f1 as { value: N; ci?: [number, number] } | undefined;
  const variantColor = (name: string) => (/^HH only/i.test(name) ? POL_COLORS.HH : /^HV only/i.test(name) ? POL_COLORS.HV : "#f2d08a");
  return (
    <div className="proof">
      <section className="proof__sec">
        <div className="bignums">
          {(
            [
              ["reference sites", h.reference_sites],
              ["training sites", h.train_sites],
              ["test sites", h.test_sites],
              ["held-out states", h.test_states],
              ["hectares scored", h.hectares_scored],
              ["NISAR passes read", h.passes_read],
              ["stages", h.stages],
              ["countries", h.countries],
            ] as [string, N][]
          )
            .filter(([, v]) => v != null)
            .map(([k, v]) => (
              <div key={k} className="bignum">
                <strong>{fmtInt(v as number)}</strong>
                <span>{k}</span>
              </div>
            ))}
        </div>
      </section>

      {moves.length > 0 && (
        <section className="proof__sec">
          <h2 className="proof__h">Each move, on states the model never saw</h2>
          <p className="proof__p">
            AUPRC rewards finding the real changes without crying wolf. It only means something next to the base rate, the score of a random guess.
            {macro?.value != null && (
              <>
                {" "}
                Macro F1 across moves: <strong>{macro.value.toFixed(2)}</strong> {macro.ci && <CI lo={macro.ci[0]} hi={macro.ci[1]} />}.
              </>
            )}
          </p>
          <IntervalChart
            rows={moves.map((m) => ({
              label: (m.name as string) ?? MOVE_NAMES[m.id as string] ?? String(m.id),
              value: m.auprc as N,
              lo: (m.auprc_ci as number[] | undefined)?.[0],
              hi: (m.auprc_ci as number[] | undefined)?.[1],
              base: m.base_rate as N,
              color: MOVE_COLORS[m.id as string],
            }))}
          />
          <table className="ptable">
            <thead>
              <tr>
                <th>Move</th>
                <th>Reference</th>
                <th>AUPRC</th>
                <th>Base rate</th>
                <th>Precision</th>
                <th>Recall</th>
                <th>F1</th>
                <th>Test hectares</th>
              </tr>
            </thead>
            <tbody>
              {moves.map((m) => (
                <tr key={String(m.id)}>
                  <td>
                    <i className="dot" style={{ background: MOVE_COLORS[m.id as string] }} />
                    {String(m.name ?? m.id)}
                  </td>
                  <td>{String(m.reference ?? "")}</td>
                  <td>
                    {num(m.auprc as N)} <CI lo={(m.auprc_ci as number[] | undefined)?.[0]} hi={(m.auprc_ci as number[] | undefined)?.[1]} />
                  </td>
                  <td>{num(m.base_rate as N, 3)}</td>
                  <td>{num(m.precision as N)}</td>
                  <td>{num(m.recall as N)}</td>
                  <td>
                    {num(m.f1 as N)} <CI lo={(m.f1_ci as number[] | undefined)?.[0]} hi={(m.f1_ci as number[] | undefined)?.[1]} />
                  </td>
                  <td>{m.n_test_blocks != null ? fmtInt(m.n_test_blocks as number) : "not measured"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {pol && pol.variants?.length > 0 && (
        <section className="proof__sec">
          <h2 className="proof__h">Which partner carries each move</h2>
          <p className="proof__p">The polarization report card: the same model retrained with HH only, HV only, and both. The gap shows what each partner carries.</p>
          <div className="legendrow">
            {pol.variants.map((v) => (
              <span key={v.name}>
                <i style={{ background: variantColor(v.name) }} />
                {v.name}
              </span>
            ))}
          </div>
          <div className="smallmult">
            {pol.classes.map((c) => (
              <div key={c} className="smallmult__cell">
                <h3>
                  <i style={{ background: MOVE_COLORS[c] }} />
                  {MOVE_NAMES[c] ?? c}
                </h3>
                <IntervalChart
                  rows={pol.variants.map((v) => ({
                    label: v.name,
                    value: v.auprc?.[c],
                    lo: v.auprc_ci?.[c]?.[0],
                    hi: v.auprc_ci?.[c]?.[1],
                    color: variantColor(v.name),
                  }))}
                />
              </div>
            ))}
          </div>
        </section>
      )}

      {s1 && (
        <section className="proof__sec">
          <h2 className="proof__h">NISAR against Sentinel-1, forest loss</h2>
          <p className="proof__p">
            Same {String(s1.n_sites ?? "")} sites, same hectares. L-band (24 cm) reaches through the canopy; C-band (5.6 cm) mostly sees the leaves on top.
            {s1.ratio != null && (
              <>
                {" "}
                At {pctx(s1.recall as N)} recall, NISAR's alerts were right {pctx(s1.precision_nisar as N)} of the time and Sentinel-1's {pctx(s1.precision_s1 as N)}:{" "}
                <strong>{(s1.ratio as number).toFixed(1)} times</strong> more often.
              </>
            )}
          </p>
          <IntervalChart
            rows={[
              { label: "NISAR (L-band)", value: s1.auprc_nisar as N, lo: (s1.auprc_nisar_ci as number[] | undefined)?.[0], hi: (s1.auprc_nisar_ci as number[] | undefined)?.[1], color: "#f2d08a" },
              { label: "Sentinel-1 (C-band)", value: s1.auprc_s1 as N, lo: (s1.auprc_s1_ci as number[] | undefined)?.[0], hi: (s1.auprc_s1_ci as number[] | undefined)?.[1], color: "#8f8d86" },
            ]}
            max={0.6}
          />
        </section>
      )}

      {cc.length > 0 && (
        <section className="proof__sec">
          <h2 className="proof__h">Another continent</h2>
          <p className="proof__p">Trained on United States sites only, then scored abroad against independent reference maps.</p>
          <IntervalChart
            rows={cc.map((c) => ({
              label: `${MOVE_NAMES[c.move as string] ?? c.move}, ${c.stage}`,
              value: c.auprc as N,
              base: c.base_rate as N,
              color: MOVE_COLORS[c.move as string],
            }))}
          />
        </section>
      )}

      {conf && conf.classes?.length > 0 && (
        <section className="proof__sec">
          <h2 className="proof__h">Where it gets confused</h2>
          <Confusion classes={conf.classes} m={conf.rows_true_cols_pred} />
        </section>
      )}

      {limits.length > 0 && (
        <section className="proof__sec">
          <h2 className="proof__h">What we cannot claim</h2>
          <ul className="limits">
            {limits.map((l, i) => (
              <li key={i}>{l}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function num(v: N, d = 2) {
  return v == null ? "not measured" : v.toFixed(d);
}

function pctx(v: N) {
  return v == null ? "an unmeasured rate" : `${Math.round(v * 100)}%`;
}

function Confusion({ classes, m }: { classes: string[]; m: number[][] }) {
  const rowSums = m.map((r) => r.reduce((a, b) => a + b, 0) || 1);
  return (
    <div className="confusion" style={{ gridTemplateColumns: `120px repeat(${classes.length}, minmax(0, 1fr))` }}>
      <div />
      {classes.map((c) => (
        <div key={`h${c}`} className="confusion__h">
          {MOVE_NAMES[c] ?? c}
        </div>
      ))}
      {m.map((row, i) => (
        <div key={`r${i}`} style={{ display: "contents" }}>
          <div className="confusion__h confusion__h--row">{MOVE_NAMES[classes[i]] ?? classes[i]}</div>
          {row.map((v, j) => {
            const f = v / rowSums[i];
            return (
              <div key={j} className="confusion__c" style={{ background: `rgba(242, 208, 138, ${0.05 + f * 0.75})`, color: f > 0.5 ? "#1b1508" : undefined }} title={`${fmtInt(v)} hectares`}>
                {Math.round(f * 100)}%
              </div>
            );
          })}
        </div>
      ))}
      <div className="confusion__note">Rows: the reference says. Columns: the model says. Each row sums to 100%.</div>
    </div>
  );
}

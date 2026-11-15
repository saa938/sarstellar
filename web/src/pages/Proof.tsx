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
      [{fmtSmall(lo)}, {fmtSmall(hi)}]
    </span>
  );
}

function fmtSmall(v: number) {
  if (v === 0) return "0";
  if (Math.abs(v) < 0.01) return v.toFixed(4);
  if (Math.abs(v) < 0.1) return v.toFixed(3);
  return v.toFixed(2);
}

const pct = (v: N, d?: number) => (v == null ? "not measured" : `${(v * 100).toFixed(d ?? (Math.abs(v) < 0.1 ? 1 : 0))}%`);

function times(r: number) {
  if (!Number.isFinite(r)) return "?";
  if (r >= 10) return `${Math.round(r)}×`;
  return `${r.toFixed(1)}×`;
}

// ---------------------------------------------------------------- log-scale interval chart

const LO = 0.001;
const HI = 1;
function lx(v: number, x0: number, x1: number) {
  const c = Math.min(Math.max(v, LO), HI);
  return x0 + ((Math.log10(c) - Math.log10(LO)) / (Math.log10(HI) - Math.log10(LO))) * (x1 - x0);
}

/** One row: chance (base rate) as a tick, the model as a dot with its 95% interval, on a log axis. */
function SkillBar({ value, lo, hi, base, color, axis = false }: { value: N; lo?: N; hi?: N; base?: N; color: string; axis?: boolean }) {
  const W = 420;
  const H = axis ? 46 : 26;
  const x0 = 8;
  const x1 = W - 8;
  const y = 13;
  return (
    <svg className="skillbar" viewBox={`0 0 ${W} ${H}`} width="100%" preserveAspectRatio="none" role="img" aria-label={value != null ? `AUPRC ${fmtSmall(value)}${base != null ? `, chance ${fmtSmall(base)}` : ""}` : "not measured"}>
      <line x1={x0} x2={x1} y1={y} y2={y} className="skillbar__rail" />
      {[0.001, 0.01, 0.1, 1].map((t) => (
        <g key={t}>
          <line x1={lx(t, x0, x1)} x2={lx(t, x0, x1)} y1={y - 4} y2={y + 4} className="skillbar__grid" />
          {axis && (
            <text x={lx(t, x0, x1)} y={H - 4} textAnchor="middle" className="chart__tick">
              {t}
            </text>
          )}
        </g>
      ))}
      {base != null && value != null && <line x1={lx(base, x0, x1)} x2={lx(value, x0, x1)} y1={y} y2={y} className="skillbar__gap" style={{ stroke: color }} />}
      {lo != null && hi != null && <line x1={lx(lo, x0, x1)} x2={lx(hi, x0, x1)} y1={y} y2={y} className="skillbar__ci" style={{ stroke: color }} />}
      {base != null && <line x1={lx(base, x0, x1)} x2={lx(base, x0, x1)} y1={y - 9} y2={y + 9} className="skillbar__base" />}
      {value != null && <circle cx={lx(value, x0, x1)} cy={y} r={6} fill={color} stroke="#06070b" strokeWidth={2} />}
    </svg>
  );
}

// ---------------------------------------------------------------- linear interval chart (Sentinel-1)

interface Row {
  label: string;
  value: N;
  lo?: N;
  hi?: N;
  color?: string;
}

function IntervalChart({ rows, max = 1, unit = "AUPRC" }: { rows: Row[]; max?: number; unit?: string }) {
  const W = 640;
  const rowH = 36;
  const ml = 170;
  const mr = 60;
  const H = rows.length * rowH + 34;
  const X = (v: number) => ml + (Math.min(Math.max(v, 0), max) / max) * (W - ml - mr);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);
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
          const y = 18 + i * rowH;
          return (
            <g key={r.label}>
              <text x={ml - 12} y={y + 4} textAnchor="end" className="ichart__label">
                {r.label}
              </text>
              {r.lo != null && r.hi != null && <line x1={X(r.lo)} x2={X(r.hi)} y1={y} y2={y} className="ichart__ci" style={{ stroke: r.color }} />}
              {r.value != null && <circle cx={X(r.value)} cy={y} r={6} fill={r.color ?? "#efede6"} stroke="#06070b" strokeWidth={2} />}
              {r.value != null && (
                <text x={W - mr + 10} y={y + 4} className="ichart__val">
                  {r.value.toFixed(3)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <figcaption>{unit}, dots with 95% intervals.</figcaption>
    </figure>
  );
}

// ---------------------------------------------------------------- page

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
        <p className="act__lede" style={{ maxWidth: 780 }}>
          Every number here comes from the pipeline, scored on places the model never trained on, against independent reference maps. Intervals are 95%
          and resample whole sites, so they show how much results vary from place to place. What we could not show, we say.
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
  const any = p.any_move as { precision?: N; recall?: N; base_rate?: N } | undefined;
  const model = p.model as { note?: string; features?: string[] } | undefined;
  const gate = p.gate as { hv_db?: N; hh_db?: N } | undefined;
  const gain = p.importance_gain as Record<string, number> | undefined;
  const baseOf = (id: string) => moves.find((m) => m.id === id)?.base_rate as N;
  const variantColor = (name: string) => (/^HH only/i.test(name) ? POL_COLORS.HH : /^HV only/i.test(name) ? POL_COLORS.HV : "#f2d08a");

  return (
    <div className="proof">
      <section className="proof__sec">
        <div className="bignums">
          {(
            [
              ["reference sites", h.reference_sites],
              ["used to learn", h.train_sites],
              ["held out", h.test_sites],
              ["states never seen", h.test_states],
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
          <h2 className="proof__h">Each move against chance</h2>
          <p className="proof__p">
            AUPRC asks how well the model ranks the hectares that really changed above the ones that did not. A random guess scores the base rate, the
            share of hectares that really did that move. On this log scale the tick is chance and the dot is the model; the gap between them is the skill.
          </p>
          <div className="skill">
            <div className="skill__head">
              <span>Move and reference</span>
              <span>AUPRC on held-out states (log scale)</span>
              <span>Against chance</span>
              <span>On the maps</span>
            </div>
            {moves.map((m) => {
              const id = String(m.id);
              const auprc = m.auprc as N;
              const ci = m.auprc_ci as [number, number] | undefined;
              const base = m.base_rate as N;
              const lift = (m.lift as N) ?? (auprc != null && base ? auprc / base : null);
              const overlaps = ci && base != null ? ci[0] <= base : false;
              const color = MOVE_COLORS[id] ?? "#efede6";
              return (
                <div key={id} className={`skill__row ${overlaps ? "is-null" : ""}`}>
                  <div className="skill__name">
                    <strong>
                      <i style={{ background: id === "still" ? "#c4c8d6" : color }} />
                      {String(m.name ?? MOVE_NAMES[id] ?? id)}
                    </strong>
                    <span>{String(m.reference ?? "")}</span>
                  </div>
                  <div className="skill__bar">
                    <SkillBar value={auprc} lo={ci?.[0]} hi={ci?.[1]} base={base} color={id === "still" ? "#c4c8d6" : color} />
                    <span className="skill__nums">
                      {auprc != null ? fmtSmall(auprc) : "not measured"} <CI lo={ci?.[0]} hi={ci?.[1]} /> · chance {base != null ? fmtSmall(base) : "?"}
                    </span>
                  </div>
                  <div className="skill__lift">
                    <strong>{lift != null ? times(lift) : "?"}</strong>
                    <span>{overlaps ? (lift != null && lift < 1.15 ? "no better than chance" : "interval includes chance") : "better than chance"}</span>
                  </div>
                  <div className="skill__maps">
                    <span>
                      precision <b>{pct(m.precision as N)}</b>
                    </span>
                    <span>
                      recall <b>{pct(m.recall as N)}</b>
                    </span>
                    {m.n_test_blocks != null && <span className="dim">{fmtInt(m.n_test_blocks as number)} reference hectares</span>}
                  </div>
                </div>
              );
            })}
            <div className="skill__axis">
              <span />
              <SkillBar value={null} color="#fff" axis />
              <span />
              <span />
            </div>
          </div>
          <div className="proof__notes">
            {model?.note && (
              <p>
                <b>How to read precision and recall.</b> {model.note}
                {gate?.hv_db != null && gate?.hh_db != null ? ` (gate: HV ${gate.hv_db} dB, HH ${gate.hh_db} dB)` : ""}
              </p>
            )}
            {any && any.precision != null && (
              <p>
                <b>Any move at all.</b> When a map names a move, it is a real change {pct(any.precision)} of the time, against {pct(any.base_rate)} of hectares that
                really changed. It finds {pct(any.recall)} of them.
              </p>
            )}
            {macro?.value != null && (
              <p>
                <b>Macro F1</b> across the moves: {macro.value.toFixed(2)} <CI lo={macro.ci?.[0]} hi={macro.ci?.[1]} />.
              </p>
            )}
            <p>
              <b>The Vanish shows no skill.</b> Open-water floods were not separable from two L-band passes at the reference flood sites: its dot sits on
              chance. We show it anyway; see the limits below.
            </p>
          </div>
        </section>
      )}

      {pol && pol.variants?.length > 0 && (
        <section className="proof__sec">
          <h2 className="proof__h">Which partner carries each move</h2>
          <p className="proof__p">
            The polarization report card: the same model retrained with HH only, HV only, and both. This is the measured answer to which polarization
            highlights each change.
            {(() => {
              const hv = pol.variants.find((v) => /^HV only/i.test(v.name))?.auprc?.fall;
              const hh = pol.variants.find((v) => /^HH only/i.test(v.name))?.auprc?.fall;
              return hv != null && hh != null && hh > 0 ? ` Forest loss is an HV move: HV alone scores ${times(hv / hh)} higher than HH alone.` : "";
            })()}
          </p>
          <div className="legendrow">
            {pol.variants.map((v) => (
              <span key={v.name}>
                <i style={{ background: variantColor(v.name) }} />
                {v.name}
              </span>
            ))}
            <span>
              <i className="legendrow__tick" />
              chance
            </span>
          </div>
          <div className="smallmult">
            {pol.classes.map((c) => (
              <div key={c} className="smallmult__cell">
                <h3>
                  <i style={{ background: MOVE_COLORS[c] }} />
                  {MOVE_NAMES[c] ?? c}
                </h3>
                {pol.variants.map((v) => (
                  <div key={v.name} className="polrow">
                    <span className="polrow__name">{v.name}</span>
                    <SkillBar value={v.auprc?.[c]} lo={v.auprc_ci?.[c]?.[0]} hi={v.auprc_ci?.[c]?.[1]} base={baseOf(c)} color={variantColor(v.name)} />
                    <span className="polrow__val">{v.auprc?.[c] != null ? fmtSmall(v.auprc[c] as number) : "not measured"}</span>
                  </div>
                ))}
                <div className="polrow polrow--axis">
                  <span />
                  <SkillBar value={null} color="#fff" axis />
                  <span />
                </div>
              </div>
            ))}
          </div>
          {gain && (
            <div className="gain">
              <div className="eyebrow">What the model listens to most (feature gain)</div>
              {(() => {
                const total = Object.values(gain).reduce((a, b) => a + b, 0) || 1;
                const names: Record<string, string> = { d_HV: "Change in HV", d_HH: "Change in HH", d_R: "Change in the HH/HV ratio" };
                return Object.entries(gain)
                  .sort((a, b) => b[1] - a[1])
                  .map(([k, v]) => (
                    <div key={k} className="gain__row">
                      <span>{names[k] ?? k}</span>
                      <i style={{ width: `${(v / total) * 100}%`, background: k === "d_HV" ? POL_COLORS.HV : k === "d_HH" ? POL_COLORS.HH : "#f2d08a" }} />
                      <b>{Math.round((v / total) * 100)}%</b>
                    </div>
                  ));
              })()}
            </div>
          )}
        </section>
      )}

      {s1 && (
        <section className="proof__sec">
          <h2 className="proof__h">NISAR against Sentinel-1, forest loss</h2>
          <p className="proof__p">
            The same {String(s1.n_sites ?? "")} forest-loss sites and the same hectares. L-band (24 cm) reaches through the canopy; C-band (5.6 cm) mostly
            sees the leaves on top.
            {s1.ratio != null && (
              <>
                {" "}
                At {pct(s1.recall as N)} recall, NISAR's alerts were right {pct(s1.precision_nisar as N)} of the time and Sentinel-1's {pct(s1.precision_s1 as N)}:{" "}
                <strong>{times(s1.ratio as number)} more often real</strong>.
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
          <h2 className="proof__h">On the stages</h2>
          <p className="proof__p">The forest-loss model scored on two stages against optical forest-loss alerts. Only one of them is a place it never trained on.</p>
          <div className="ccards">
            {cc.map((c) => {
              const auprc = c.auprc as N;
              const base = c.base_rate as N;
              const stage = String(c.stage);
              const isHeldOut = stage === "rondonia";
              return (
                <div key={stage} className="ccard">
                  <div className={`ccard__tag ${isHeldOut ? "is-held" : ""}`}>{isHeldOut ? "Never trained on: Brazil" : "In a training state: not held out"}</div>
                  <h3>
                    <a href={`#/stage/${stage}`}>{stage === "rondonia" ? "Rondonia, Brazil" : stage === "morton" ? "Morton, Washington" : stage}</a>
                  </h3>
                  <div className="ccard__big">{auprc != null && base ? times(auprc / base) : "?"}</div>
                  <div className="dim">better than chance at ranking forest loss</div>
                  <SkillBar value={auprc} base={base} color={MOVE_COLORS.fall} axis />
                  <p>
                    AUPRC {auprc != null ? fmtSmall(auprc) : "?"} against chance {base != null ? fmtSmall(base) : "?"} · precision {pct(c.precision as N)}, recall{" "}
                    {pct(c.recall as N)} · {c.n_positive != null ? `${fmtInt(c.n_positive as number)} reference loss hectares of ` : ""}
                    {c.n_blocks != null ? fmtInt(c.n_blocks as number) : "?"}
                  </p>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {conf && conf.classes?.length > 0 && (
        <section className="proof__sec">
          <h2 className="proof__h">Where it gets confused</h2>
          <p className="proof__p">Each row is what the reference says; each column is what the model says. Read across a row to see where that move's hectares end up.</p>
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

function Confusion({ classes, m }: { classes: string[]; m: number[][] }) {
  const rowSums = m.map((r) => r.reduce((a, b) => a + b, 0) || 1);
  return (
    <div className="confusion" style={{ gridTemplateColumns: `130px repeat(${classes.length}, minmax(0, 1fr))` }}>
      <div className="confusion__corner">reference ↓ · model →</div>
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
              <div
                key={j}
                className={`confusion__c ${i === j ? "is-diag" : ""}`}
                style={{ background: `rgba(242, 208, 138, ${0.04 + f * 0.8})`, color: f > 0.45 ? "#1b1508" : undefined }}
                title={`${fmtInt(v)} hectares`}
              >
                {Math.round(f * 100)}%
              </div>
            );
          })}
        </div>
      ))}
      <div className="confusion__note">Each row sums to 100%. The diagonal is agreement.</div>
    </div>
  );
}

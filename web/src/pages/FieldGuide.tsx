import { useEffect, useState } from "react";
import { Nav } from "../components/Nav";
import { Footer } from "../components/Footer";
import { FixtureTag } from "../components/FixtureTag";
import { MiniFloor } from "../components/MiniFloor";
import { loadIndex, loadMoves, loadProof, type IndexResult, type MovesResult } from "../lib/data";
import { DEFAULT_FLOOR, MOVE_COLORS } from "../lib/moves";
import type { MoveDef } from "../lib/types";
import { StageCard } from "./Landing";
import { CI } from "./Proof";

const POL_TEXT: Record<string, string> = {
  HH: "HH hears surfaces and bounces: water, soil, trunks standing in floodwater.",
  HV: "HV hears volume: leaves, branches and crop canopies that twist the wave.",
};

export default function FieldGuide({ moveId }: { moveId?: string }) {
  const [mv, setMv] = useState<MovesResult | null>(null);
  const [idx, setIdx] = useState<IndexResult | null>(null);
  const [proof, setProof] = useState<Record<string, unknown> | null>(null);
  useEffect(() => {
    loadMoves().then(setMv);
    loadIndex().then(setIdx);
    loadProof().then(setProof);
  }, []);
  const moves = mv?.doc.moves ?? [];
  const floor = mv?.doc.floor ?? DEFAULT_FLOOR;
  const move = moveId ? moves.find((m) => m.id === moveId) : null;

  return (
    <div className="page">
      <Nav active="moves" />
      {moveId && move ? (
        <MoveDetail move={move} moves={moves} floor={floor} idx={idx} proof={proof} fixture={!!mv?.fixture} />
      ) : (
        <>
          <header className="page__head">
            <div className="eyebrow">Field guide</div>
            <h1 className="act__title">The moves</h1>
            <p className="act__lede" style={{ maxWidth: 760 }}>
              Every kind of surface change makes its own step on the floor of HH against HV. Here is each one: what happens on the ground, the physics
              behind it, which partner carries it, and where on Earth to watch it. {mv?.fixture ? "" : ""}
            </p>
            {mv?.fixture && (
              <div style={{ marginTop: 18 }}>
                <FixtureTag />
              </div>
            )}
          </header>
          <div className="page__body">
            <div className="guide">
              {moves.map((m) => (
                <a key={m.id} href={`#/moves/${m.id}`} className="guidecard" style={{ ["--mc" as string]: MOVE_COLORS[m.id] }}>
                  <MiniFloor moveId={m.id} path={m.path} floor={floor} size="lg" showLabels />
                  <div className="guidecard__body">
                    <h2>
                      <i style={{ background: MOVE_COLORS[m.id] }} />
                      {m.name}
                    </h2>
                    <p className="guidecard__what">{m.what}</p>
                    <p className="guidecard__phys">{m.physics}</p>
                    <div className="movecard__pols">
                      {m.carried_by.length ? (
                        m.carried_by.map((p) => (
                          <span key={p} className={`pol pol--${p.toLowerCase()}`}>
                            {p}
                          </span>
                        ))
                      ) : (
                        <span className="dim">No partner: the baseline</span>
                      )}
                    </div>
                  </div>
                </a>
              ))}
            </div>
          </div>
        </>
      )}
      {moveId && !move && mv && (
        <div className="page__head">
          <h1 className="act__title">No move called "{moveId}"</h1>
          <a className="btn" href="#/moves">
            Back to the field guide
          </a>
        </div>
      )}
      <Footer />
    </div>
  );
}

function MoveDetail({ move, moves, floor, idx, proof, fixture }: { move: MoveDef; moves: MoveDef[]; floor: typeof DEFAULT_FLOOR; idx: IndexResult | null; proof: Record<string, unknown> | null; fixture: boolean }) {
  const i = moves.findIndex((m) => m.id === move.id);
  const prev = moves[(i - 1 + moves.length) % moves.length];
  const next = moves[(i + 1) % moves.length];
  const stages = (idx?.index.stages ?? []).filter((s) => move.stages.includes(s.id) || s.move === move.id);
  const pm = ((proof?.moves as Record<string, unknown>[] | undefined) ?? []).find((x) => x.id === move.id) as Record<string, unknown> | undefined;
  const auprc = pm?.auprc as number | null | undefined;
  const ci = pm?.auprc_ci as [number, number] | undefined;
  const base = pm?.base_rate as number | null | undefined;
  const f1 = pm?.f1 as number | null | undefined;
  return (
    <>
      <header className="page__head movehead" style={{ ["--mc" as string]: MOVE_COLORS[move.id] }}>
        <a className="linkbtn" href="#/moves">
          ← All moves
        </a>
        <div className="movehead__grid">
          <div className="movehead__viz">
            <MiniFloor moveId={move.id} path={move.path} floor={floor} size="lg" showLabels beat={1.1} />
            {fixture && <FixtureTag className="movehead__fixture" />}
          </div>
          <div>
            <div className="eyebrow" style={{ color: MOVE_COLORS[move.id] }}>
              Move {i + 1} of {moves.length}
            </div>
            <h1 className="act__title">{move.name}</h1>
            <p className="movehead__what">{move.what}</p>
            <p className="act__lede">{move.physics}</p>
            <div className="movehead__pols">
              <div className="eyebrow">Carried by</div>
              {move.carried_by.length ? (
                move.carried_by.map((p) => (
                  <p key={p}>
                    <span className={`pol pol--${p.toLowerCase()}`}>{p}</span> {POL_TEXT[p] ?? ""}
                  </p>
                ))
              ) : (
                <p className="dim">Neither partner moves beyond speckle noise. This is the baseline every other move is measured against.</p>
              )}
            </div>
          </div>
        </div>
      </header>
      <div className="page__body">
        <div className="movefacts">
          <section>
            <div className="eyebrow">How well we recognize it</div>
            {pm && auprc != null ? (
              <div className="movefacts__metric">
                <strong>{auprc.toFixed(2)}</strong>
                <span>
                  AUPRC on held-out states {ci && <CI lo={ci[0]} hi={ci[1]} />}
                  {base != null && <> · a random guess scores {base.toFixed(3)}</>}
                  {f1 != null && <> · F1 {f1.toFixed(2)}</>}
                </span>
                {typeof pm.reference === "string" && <span className="dim">Reference: {pm.reference}</span>}
              </div>
            ) : (
              <p className="dim">Measured results arrive with the evaluation. Until then this page shows no number on purpose.</p>
            )}
          </section>
          <section>
            <div className="eyebrow">What NISAR could do next</div>
            <p className="movefacts__future">{move.future}</p>
          </section>
        </div>
        <div className="eyebrow" style={{ margin: "56px 0 18px" }}>
          Where to watch it
        </div>
        {stages.length ? (
          <div className="tour">
            {stages.map((s) => (
              <StageCard key={s.id} s={s} root={idx?.base ?? ""} />
            ))}
          </div>
        ) : (
          <p className="dim">No stage for this move is published yet.</p>
        )}
        <nav className="movenav">
          <a href={`#/moves/${prev.id}`}>
            <span className="dim">Previous</span> {prev.name}
          </a>
          <a href={`#/moves/${next.id}`}>
            <span className="dim">Next</span> {next.name}
          </a>
        </nav>
      </div>
    </>
  );
}

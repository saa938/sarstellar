import { lazy, Suspense, useEffect, useState } from "react";
import Lenis from "lenis";
import { Nav } from "../components/Nav";
import { Footer } from "../components/Footer";
import { FixtureTag } from "../components/FixtureTag";
import { MiniFloor } from "../components/MiniFloor";
import { ScatterDiagram, Meter, SURFACES, type SurfaceKind } from "../landing/ScatterDiagram";
import { FloorStory } from "../landing/FloorStory";
import { API_URL, assetUrl, loadIndex, loadMoves, loadProof, type IndexResult, type MovesResult } from "../lib/data";
import { DEFAULT_FLOOR, MOVE_COLORS, MOVE_NAMES } from "../lib/moves";
import { fmtInt, fmtMonthYear } from "../lib/format";
import type { MoveDef, StageIndexEntry } from "../lib/types";
import { prefersReducedMotion } from "../stage/clock";

const Globe = lazy(() => import("../landing/Globe"));

export function pickStage(stages: StageIndexEntry[], prefer: string[], dualPol = false) {
  for (const id of prefer) {
    const s = stages.find((x) => x.id === id);
    if (s && (!dualPol || s.move !== "melt")) return s;
  }
  return stages.find((s) => !dualPol || s.move !== "melt") ?? stages[0] ?? null;
}

export function useLenis() {
  useEffect(() => {
    if (prefersReducedMotion()) return;
    const lenis = new Lenis({ autoRaf: true, lerp: 0.11, smoothWheel: true });
    return () => lenis.destroy();
  }, []);
}

export default function Landing() {
  const [idx, setIdx] = useState<IndexResult | null>(null);
  const [mv, setMv] = useState<MovesResult | null>(null);
  const [proof, setProof] = useState<Record<string, unknown> | null | undefined>(undefined);
  const [scrolled, setScrolled] = useState(false);
  const [globeReady, setGlobeReady] = useState(false);

  useEffect(() => {
    loadIndex().then(setIdx);
    loadMoves().then(setMv);
    loadProof().then(setProof);
  }, []);
  useLenis();
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 40);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);

  const stages = idx?.index.stages ?? [];
  const heroStage = pickStage(stages, ["punjab", "rondonia", "morton", "village-creek", "sylhet"]);
  const floorStage = pickStage(stages, ["punjab", "rondonia", "morton", "sylhet", "indiana", "village-creek"], true);
  const moves = mv?.doc.moves ?? [];
  const floor = mv?.doc.floor ?? DEFAULT_FLOOR;
  const anyFixture = !!(idx?.fixture || mv?.fixture);
  const heroMoves = ["fall", "bounce", "waltz", "vanish", "melt"].map((id) => moves.find((m) => m.id === id)).filter(Boolean) as MoveDef[];

  return (
    <div className="landing">
      <Nav variant="overlay" active="landing" className={scrolled ? "is-scrolled" : ""} />

      {/* Act one: overture */}
      <section className="act act--overture">
        <div className={`overture__globe ${globeReady ? "is-ready" : ""}`}>
          <Suspense fallback={null}>{idx && <Globe stages={stages} onReady={() => setGlobeReady(true)} fill={0.43} />}</Suspense>
        </div>
        <div className="overture__shade" />
        <div className="overture__copy">
          <div className="eyebrow">NASA Space Apps 2026 · Dancing with the SARs</div>
          <h1 className="hero">
            Earth is dancing.
            <br />
            <em>NISAR can see the steps.</em>
          </h1>
          <p className="hero__sub">
            Every 12 days, through clouds and darkness, NISAR, the NASA-ISRO radar satellite, listens to every hectare of land. Each kind of change moves
            in its own way: forests fall, floods bounce, fields waltz. Here you can watch the dance.
          </p>
          <div className="hero__ctas">
            {heroStage && (
              <a className="btn btn--primary" href={`#/stage/${heroStage.id}`}>
                Watch {heroStage.name} dance <span className="arrow">→</span>
              </a>
            )}
            <a className="btn" href="#partners">
              How to read the dance
            </a>
          </div>
          {heroMoves.length > 0 && (
            <div className="hero__moves" aria-label="Five of the moves">
              {heroMoves.map((m) => (
                <a key={m.id} className="glyph" href={`#/moves/${m.id}`}>
                  <MiniFloor moveId={m.id} path={m.path} floor={floor} size="sm" beat={0.75} />
                  <span>
                    <i style={{ background: MOVE_COLORS[m.id] }} />
                    {m.name}
                  </span>
                </a>
              ))}
            </div>
          )}
        </div>
        <a className="overture__scroll" href="#partners" aria-label="Scroll to the story">
          <span>Scroll</span>
          <i />
        </a>
        {anyFixture && <FixtureTag className="overture__fixture" />}
      </section>

      {/* Act two: the two partners */}
      <section className="act act--partners" id="partners">
        <div className="act__inner">
          <div className="act__head">
            <div className="eyebrow">Act two · The two partners</div>
            <h2 className="act__title">Two ways the radar listens</h2>
            <p className="act__lede">
              NISAR sends down a pulse of microwaves about 24 centimeters long and records what comes back. It listens in two ways.{" "}
              <b className="pol pol--hh">HH</b> sends and listens with the wave flat: it hears surfaces and bounces. <b className="pol pol--hv">HV</b> sends flat and
              listens upright, so only things that twist the wave answer, like leaves and branches. Every surface sounds different to the two partners.
            </p>
          </div>
          <div className="partners">
            {(Object.keys(SURFACES) as SurfaceKind[]).map((k) => (
              <article key={k} className="partner">
                <ScatterDiagram kind={k} />
                <div className="partner__body">
                  <div className="partner__mech">{SURFACES[k].mech}</div>
                  <h3>{SURFACES[k].title}</h3>
                  <p>{SURFACES[k].text}</p>
                  <div className="partner__meters">
                    <Meter label="HH hears" value={SURFACES[k].hh} pol="hh" />
                    <Meter label="HV hears" value={SURFACES[k].hv} pol="hv" />
                  </div>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* Act three: the dance floor (scroll story) */}
      <FloorStory entry={floorStage} />

      {/* Act four: the moves */}
      <section className="act act--moves" id="moves">
        <div className="act__inner">
          <div className="act__head">
            <div className="eyebrow">Act four · The moves</div>
            <h2 className="act__title">Eight moves, one vocabulary</h2>
            <p className="act__lede">Each kind of change has its own step on the floor. Learn them once and you can read any place NISAR flies over.</p>
          </div>
          <div className="movegrid">
            {moves.map((m) => (
              <a key={m.id} href={`#/moves/${m.id}`} className="movecard" style={{ ["--mc" as string]: MOVE_COLORS[m.id] }}>
                <MiniFloor moveId={m.id} path={m.path} floor={floor} size="md" />
                <div className="movecard__body">
                  <h3>{m.name}</h3>
                  <p>{m.what}</p>
                  <div className="movecard__pols">
                    {m.carried_by.length ? (
                      m.carried_by.map((p) => (
                        <span key={p} className={`pol pol--${p.toLowerCase()}`}>
                          {p}
                        </span>
                      ))
                    ) : (
                      <span className="dim">no partner moves</span>
                    )}
                  </div>
                </div>
              </a>
            ))}
            {!moves.length && <p className="dim">The field guide is loading.</p>}
          </div>
        </div>
      </section>

      {/* Act five: world tour */}
      <section className="act act--tour" id="tour">
        <div className="act__inner">
          <div className="act__head">
            <div className="eyebrow">Act five · The world tour</div>
            <h2 className="act__title">Stages around the world</h2>
            <p className="act__lede">Each stage is a real place NISAR has watched since its first months in orbit. Open one and press play.</p>
          </div>
          <div className="tour">
            {stages.map((s) => (
              <StageCard key={s.id} s={s} root={idx?.base ?? ""} />
            ))}
          </div>
        </div>
      </section>

      {/* Act six: how we know */}
      <section className="act act--proof" id="proof">
        <div className="act__inner">
          <div className="act__head">
            <div className="eyebrow">Act six · How we know</div>
            <h2 className="act__title">Measured, not imagined</h2>
          </div>
          <ProofTeaser proof={proof} />
        </div>
      </section>

      {/* Act seven: your stage */}
      <section className="act act--yours">
        <div className="act__inner yours">
          <div>
            <div className="eyebrow">Act seven · Your stage</div>
            <h2 className="act__title">Watch any place dance</h2>
            <p className="act__lede">
              Open any stage, brush the floor to light up hectares on the map, or draw a box on the map to see how those hectares move.
              {API_URL ? " Or draw a new box anywhere NISAR has flown and watch the dance assemble pass by pass." : ""}
            </p>
            <div className="hero__ctas">
              <a className="btn btn--primary" href="#/explore">
                Explore every stage <span className="arrow">→</span>
              </a>
              <a className="btn" href="#/moves">
                Field guide
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* Act eight: the next season */}
      <section className="act act--future" id="future">
        <div className="act__inner">
          <div className="act__head">
            <div className="eyebrow">Act eight · The next season</div>
            <h2 className="act__title">What NISAR could do next</h2>
            <p className="act__lede">Every move is also a job. These are the ones NISAR is built for.</p>
          </div>
          <ol className="future">
            {moves
              .filter((m) => m.future)
              .map((m) => (
                <li key={m.id}>
                  <span className="future__move">
                    <i style={{ background: MOVE_COLORS[m.id] }} />
                    {MOVE_NAMES[m.id] ?? m.name}
                  </span>
                  <span className="future__text">{m.future}</span>
                </li>
              ))}
          </ol>
        </div>
      </section>

      <Footer />
    </div>
  );
}

export function StageCard({ s, root }: { s: StageIndexEntry; root: string }) {
  return (
    <a className="stagecard" href={`#/stage/${s.id}`}>
      <div className="stagecard__img">
        <img src={assetUrl(root, s.thumb)} alt={`NISAR radar image of ${s.name}`} loading="lazy" />
        <span className="stagecard__move" style={{ ["--mc" as string]: MOVE_COLORS[s.move] ?? "#ccc" }}>
          <i />
          {MOVE_NAMES[s.move] ?? s.move}
        </span>
      </div>
      <div className="stagecard__body">
        <div className="eyebrow">
          {s.name} · {s.country}
        </div>
        <h3>{s.title}</h3>
        <p>{s.teaser}</p>
        <div className="stagecard__meta">
          {s.n_passes} passes · {fmtMonthYear(s.first)} to {fmtMonthYear(s.last)}
        </div>
      </div>
    </a>
  );
}

type Num = number | null | undefined;
const pct = (v: Num) => (v == null ? "not measured" : `${Math.round(v * 100)}%`);

export function ProofTeaser({ proof }: { proof: Record<string, unknown> | null | undefined }) {
  if (proof === undefined) return <div className="proofwait" />;
  if (!proof) {
    return (
      <div className="proofwait">
        <p className="act__lede">Measured results arrive here as the evaluation finishes. Until then, this is how they are made:</p>
        <ol className="method">
          <li>
            <strong>Learn the steps on places where we know the answer.</strong> Reference sites with independent labels: optical forest-loss alerts,
            fire perimeters, water maps, crop maps.
          </li>
          <li>
            <strong>Test on places the model never saw.</strong> Whole states held out, and a second continent, so a score cannot come from memorizing a
            place.
          </li>
          <li>
            <strong>Report every number with an interval.</strong> Plus a polarization report card: retrain with HH only, HV only and both, and measure
            what each partner carries.
          </li>
        </ol>
      </div>
    );
  }
  const h = (proof.headline ?? {}) as Record<string, Num>;
  const s1 = (proof.sentinel1 ?? null) as Record<string, unknown> | null;
  const stats: [string, Num][] = [
    ["reference sites", h.reference_sites],
    ["hectares scored", h.hectares_scored],
    ["NISAR passes read", h.passes_read],
    ["stages", h.stages],
    ["countries", h.countries],
  ];
  return (
    <div className="proofteaser">
      <div className="bignums">
        {stats
          .filter(([, v]) => v != null)
          .map(([k, v]) => (
            <div key={k} className="bignum">
              <strong>{fmtInt(v as number)}</strong>
              <span>{k}</span>
            </div>
          ))}
      </div>
      {s1 && (s1.ratio as Num) != null && (
        <div className="callout">
          <div className="callout__big">{(s1.ratio as number).toFixed(1)}×</div>
          <div>
            <p>
              At the same detection rate ({pct(s1.recall as Num)} of real losses found), NISAR's forest-loss alerts were right {pct(s1.precision_nisar as Num)} of
              the time, Sentinel-1's {pct(s1.precision_s1 as Num)}, across {String(s1.n_sites ?? "?")} sites.
            </p>
            <p className="dim">L-band reaches through the canopy; C-band mostly sees the leaves on top.</p>
          </div>
        </div>
      )}
      <a className="btn" href="#/proof">
        All the evidence, with intervals <span className="arrow">→</span>
      </a>
    </div>
  );
}

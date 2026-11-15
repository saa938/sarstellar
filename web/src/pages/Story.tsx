import { useEffect, useMemo, useRef, useState } from "react";
import { Nav } from "../components/Nav";
import { Footer } from "../components/Footer";
import { loadIndex, loadStory, publicUrl, type StoryResult } from "../lib/data";
import type { Measure, ProofItem, StoryDoc, StoryExample } from "../lib/story";
import { StoryChart } from "../chart/StoryChart";
import { HHLine } from "../chart/HHLine";
import { reducedMotion } from "../chart/dots";
import { DB_NOTE } from "../lib/labels";
import { fmtDate } from "../lib/format";

/** Adds "is-in" once the element scrolls into view (opacity/transform reveals only). */
export function useReveal<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (reducedMotion()) {
      el.classList.add("is-in");
      return;
    }
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          el.classList.add("is-in");
          io.disconnect();
        }
      },
      { threshold: 0.12, rootMargin: "0px 0px -6% 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return ref;
}

export default function Story() {
  const [story, setStory] = useState<StoryResult | null | undefined>(undefined);
  const [nPlaces, setNPlaces] = useState(9);
  useEffect(() => {
    loadStory().then(setStory);
    loadIndex().then((r) => setNPlaces(r.index.stages.length || 9));
  }, []);
  const doc = story?.doc;
  return (
    <div className="storypage">
      <Nav variant="overlay" active="story" />
      {story === null && (
        <div className="page__head">
          <p className="dim">The story is not available yet.</p>
        </div>
      )}
      {doc && (
        <>
          <Hero doc={doc} />
          <Channels doc={doc} />
          {doc.examples.map((ex, i) => (
            <Example key={ex.id} ex={ex} i={i} n={doc.examples.length} />
          ))}
          <Proof doc={doc} />
          <Applications doc={doc} nPlaces={nPlaces} />
        </>
      )}
      <Footer />
      {story?.placeholder && <div className="placeholder-tag">Placeholder story: the real story.json has not landed yet</div>}
    </div>
  );
}

// ---------------------------------------------------------------- hero

function Hero({ doc }: { doc: StoryDoc }) {
  const frames = doc.hero.frames;
  const [i, setI] = useState(0);
  const [front, setFront] = useState(0); // which of the two layers is on top
  const [srcs, setSrcs] = useState<[string, string]>([frames[0] ? publicUrl(frames[0].image) : "", ""]);
  useEffect(() => {
    if (frames.length < 2 || reducedMotion()) return;
    let dead = false;
    let k = 0;
    let timer = 0;
    const step = () => {
      const next = (k + 1) % frames.length;
      const url = publicUrl(frames[next].image);
      const img = new Image();
      img.src = url;
      const show = () => {
        if (dead) return;
        k = next;
        setSrcs((s) => {
          const back = front === 0 ? 1 : 0;
          const out: [string, string] = [...s] as [string, string];
          out[back] = url;
          return out;
        });
        setFront((f) => (f === 0 ? 1 : 0));
        setI(next);
        timer = window.setTimeout(step, 3400);
      };
      img.decode().then(show, show);
    };
    timer = window.setTimeout(step, 2600);
    return () => {
      dead = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frames]);
  const f = frames[i];
  return (
    <section className="hero2">
      <div className="hero2__img">
        {srcs.map((s, j) => (s ? <img key={j} src={s} alt="" className={j === front ? "is-on" : ""} decoding="async" /> : null))}
      </div>
      <div className="hero2__shade" />
      <div className="hero2__copy">
        <h1>{doc.hero.title}</h1>
        <p>{doc.hero.subtitle}</p>
      </div>
      <div className="hero2__stamp">
        <span>{doc.hero.place}</span>
        {f && <span className="mono">NISAR radar · {fmtDate(f.date)}</span>}
      </div>
      <a className="hero2__cue" href="#channels" onClick={(e) => { e.preventDefault(); document.getElementById("channels")?.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth" }); }}>
        <span>Scroll</span>
        <i />
      </a>
    </section>
  );
}

// ---------------------------------------------------------------- two ways it listens

function Channels({ doc }: { doc: StoryDoc }) {
  const ch = doc.channels;
  const [active, setActive] = useState<string | null>(null);
  const ref = useReveal<HTMLElement>();
  const marks = useMemo(() => ch.chips.map((c) => ({ id: c.id, HH: c.HH, HV: c.HV, label: c.label })), [ch]);
  return (
    <section className="sec channels reveal" id="channels" ref={ref}>
      <div className="sec__inner channels__grid">
        <div className="channels__text">
          <div className="eyebrow">How the radar sees</div>
          <h2 className="sec__title">{ch.title}</h2>
          {ch.text.map((t, i) => (
            <p key={i} className="sec__lede">
              {t}
            </p>
          ))}
          {!ch.text.some((t) => /decibel/i.test(t)) && <p className="sec__note">dB means {DB_NOTE}.</p>}
        </div>
        <div className="channels__chart">
          <StoryChart cloud={ch.cloud} marks={marks} active={active} ariaLabel="Each surface placed by its two echoes: HH across, HV up" />
          <p className="chart-caption">Each faint dot is one hectare of farmland, forest, water and town. The labeled dots are the five places below.</p>
        </div>
      </div>
      <div className="sec__inner">
          <ul className="chips">
            {ch.chips.map((c) => (
              <li key={c.id}>
                <button
                  className={`chip2 ${active === c.id ? "is-on" : ""}`}
                  onMouseEnter={() => setActive(c.id)}
                  onMouseLeave={() => setActive(null)}
                  onFocus={() => setActive(c.id)}
                  onBlur={() => setActive(null)}
                  onClick={() => setActive(active === c.id ? null : c.id)}
                >
                  <span className="chip2__img">
                    <img src={publicUrl(c.image)} alt={`Radar image: ${c.label}`} loading="lazy" decoding="async" />
                  </span>
                  <span className="chip2__body">
                    <strong>{c.label}</strong>
                    <span>{c.text}</span>
                    <em>
                      {c.place} · {fmtDate(c.date)}
                    </em>
                  </span>
                </button>
              </li>
            ))}
          </ul>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- examples

function MeasureView({ m }: { m: Measure | undefined }) {
  if (m == null) return null;
  if (typeof m === "string" || typeof m === "number") return <div className="measure"><strong>{m}</strong></div>;
  return (
    <div className="measure">
      <strong>
        {m.value}
        {m.unit ? <span className="measure__unit">{m.unit}</span> : null}
      </strong>
      {m.label && <span>{m.label}</span>}
    </div>
  );
}

function Example({ ex, i, n }: { ex: StoryExample; i: number; n: number }) {
  const ref = useReveal<HTMLElement>();
  return (
    <section className="sec example reveal" ref={ref} id={`ex-${ex.id}`}>
      <div className="sec__inner example__grid">
        <div className="example__text">
          <div className="eyebrow">
            Example {i + 1} of {n} · {ex.kicker}
          </div>
          <h2 className="sec__title">{ex.title}</h2>
          <p className="sec__lede">{ex.text}</p>
          <MeasureView m={ex.measure} />
        </div>
        <div className="example__crops">
          {[ex.before, ex.after].map((f, j) => (
            <figure key={j} className="crop">
              <div className="crop__img">
                <img src={publicUrl(f.image)} alt={`Radar image, ${j ? "after" : "before"}: ${fmtDate(f.date)}`} loading="lazy" decoding="async" />
              </div>
              <figcaption>
                <span>{j ? "After" : "Before"}</span> {fmtDate(f.date)}
              </figcaption>
            </figure>
          ))}
        </div>
        <div className="example__chart">
          {ex.one_d && ex.series ? (
            <HHLine series={ex.series} ariaLabel={`${ex.title}: HH over time`} />
          ) : (
            <>
              <StoryChart cloud={ex.cloud_before ?? null} cloudTo={ex.cloud_after ?? null} path={ex.path ?? null} afterDate={ex.after.date} morph zoom ariaLabel={`${ex.title}: hectares moving from before to after`} />
              <p className="chart-caption">Faint dots: hectares here, moving from the before pass to the after pass. Gold: their median, pass by pass. Axes zoomed to this example.</p>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- does it work

function DotGrid({ value, label, strong, fraction }: { value: number; label: string; strong?: boolean; fraction: boolean }) {
  const lit = Math.max(0, Math.min(100, Math.round(fraction ? value * 100 : value)));
  return (
    <div className={`dotgrid ${strong ? "dotgrid--model" : ""}`}>
      <div className="dotgrid__cells" aria-label={`${label}: ${lit} of 100`}>
        {Array.from({ length: 100 }, (_, k) => (
          <i key={k} className={k < lit ? "is-on" : ""} />
        ))}
      </div>
      <div className="dotgrid__label">
        <strong>{lit} in 100</strong>
        <span>{label}</span>
      </div>
    </div>
  );
}

function Bars({ bars }: { bars: { label: string; value: number }[] }) {
  const max = Math.max(...bars.map((b) => b.value), 1e-9);
  return (
    <div className="bars">
      {bars.map((b, i) => (
        <div key={b.label} className="bars__row">
          <span className="bars__label">{b.label}</span>
          <span className="bars__track">
            <i style={{ width: `${(b.value / max) * 100}%` }} className={i === 0 ? "is-first" : ""} />
          </span>
          <span className="bars__val">{b.value < 0.1 ? b.value.toFixed(3) : b.value < 10 ? b.value.toFixed(2) : b.value}</span>
        </div>
      ))}
    </div>
  );
}

function ProofItemView({ it }: { it: ProofItem }) {
  const ref = useReveal<HTMLDivElement>();
  return (
    <div className="pitem reveal" ref={ref}>
      <p className="pitem__statement">{it.statement}</p>
      <div className="pitem__visual">
        {it.kind === "dots" && it.model != null && it.baseline != null && (
          <div className="pitem__dots">
            <DotGrid value={it.model} label={it.model_label ?? "the model"} strong fraction={Math.max(it.model, it.baseline) <= 1} />
            <DotGrid value={it.baseline} label={it.baseline_label ?? "guessing"} fraction={Math.max(it.model, it.baseline) <= 1} />
          </div>
        )}
        {it.kind === "bars" && it.bars && <Bars bars={it.bars} />}
        {it.kind === "bars" && !it.bars && it.model != null && it.baseline != null && (
          <Bars
            bars={[
              { label: it.model_label ?? "model", value: it.model },
              { label: it.baseline_label ?? "baseline", value: it.baseline },
            ]}
          />
        )}
      </div>
      {it.detail && <p className="pitem__detail">{it.detail}</p>}
    </div>
  );
}

function Proof({ doc }: { doc: StoryDoc }) {
  const p = doc.proof;
  const ref = useReveal<HTMLDivElement>();
  return (
    <section className="sec proofsec" id="does-it-work">
      <div className="sec__inner">
        <div className="reveal" ref={ref}>
          <div className="eyebrow">Tested on places it never saw</div>
          <h2 className="sec__title">{p.title}</h2>
          {p.intro && <p className="sec__lede">{p.intro}</p>}
        </div>
        <div className="pitems">
          {p.items.map((it) => (
            <ProofItemView key={it.id} it={it} />
          ))}
        </div>
        {p.limits?.length > 0 && (
          <div className="limits2">
            <h3>What it cannot do yet</h3>
            <ul>
              {p.limits.map((l, i) => (
                <li key={i}>{l}</li>
              ))}
            </ul>
          </div>
        )}
        <a className="linkbtn" href="#/method">
          All the numbers, and how they were measured
        </a>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- applications

function Applications({ doc, nPlaces }: { doc: StoryDoc; nPlaces: number }) {
  const ref = useReveal<HTMLDivElement>();
  return (
    <section className="sec apps">
      <div className="sec__inner">
        <div className="eyebrow">What this could do</div>
        <h2 className="sec__title">Every 12 days, everywhere</h2>
        <div className="apps__grid reveal" ref={ref}>
          {doc.applications.map((a, i) => (
            <div key={i} className="appcard">
              <h3>{a.title}</h3>
              <p>{a.text}</p>
            </div>
          ))}
        </div>
        <div className="apps__cta">
          <a className="btn btn--primary" href="#/places">
            Explore the {nPlaces} places <span className="arrow">→</span>
          </a>
        </div>
      </div>
    </section>
  );
}

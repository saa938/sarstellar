import { useEffect, useMemo, useRef, useState } from "react";
import { loadDecoded, baseState, type Loaded } from "../stage/loadDecoded";
import { Clock, prefersReducedMotion } from "../stage/clock";
import { DanceFloor } from "../stage/DanceFloor";
import { useClockBeat } from "../stage/Timeline";
import { fmtDate } from "../lib/format";
import type { StageIndexEntry } from "../lib/types";

interface Step {
  title: string;
  text: string;
  emph: string | null;
  play: boolean;
}

function steps(entry: StageIndexEntry | null, hhOnly: boolean): Step[] {
  const where = entry ? `${entry.name}, ${entry.country}` : "One place";
  return [
    {
      title: `Take one place: ${where}.`,
      text: "Cut it into hectares, squares 100 meters on a side. Each hectare becomes one dot of light.",
      emph: null,
      play: false,
    },
    {
      title: "Place every dot by its two echoes.",
      text: hhOnly
        ? "Over ice NISAR listens with HH only, so this floor has one partner: across is HH on the first pass, up is HH now."
        : "Across: how loudly the hectare answers in HH. Up: how loudly it answers in HV. Loud is right and up; quiet is left and down.",
      emph: null,
      play: false,
    },
    {
      title: "The floor is a map of surfaces.",
      text: "Calm water mirrors the pulse away, so it sits in the dark corner. Bare soil and short crops answer HH but barely HV.",
      emph: "water",
      play: false,
    },
    {
      title: "Forest sits high. Double bounce sits far right.",
      text: "Leaves and branches are what HV hears, so forest rises to the top. Flooded forests and city walls fire the pulse straight back, far to the right.",
      emph: "forest",
      play: false,
    },
    {
      title: "Now press play.",
      text: "Every 12 days NISAR passes over again, and every dot takes a step. The way a dot moves tells you what happened on the ground.",
      emph: null,
      play: true,
    },
  ];
}

export function FloorStory({ entry }: { entry: StageIndexEntry | null }) {
  const ref = useRef<HTMLElement>(null);
  const [near, setNear] = useState(false);
  const [L, setL] = useState<Loaded | null>(null);
  const [active, setActive] = useState(0);
  const stepRefs = useRef<(HTMLDivElement | null)[]>([]);

  useEffect(() => {
    const io = new IntersectionObserver(([e]) => e.isIntersecting && setNear(true), { rootMargin: "1400px 0px" });
    if (ref.current) io.observe(ref.current);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!near || !entry) return;
    let dead = false;
    loadDecoded(entry.id)
      .then((x) => !dead && setL(x))
      .catch(() => undefined);
    return () => {
      dead = true;
    };
  }, [near, entry]);

  const list = useMemo(() => steps(entry, L?.hhOnly ?? false), [entry, L]);

  useEffect(() => {
    const io = new IntersectionObserver(
      (es) => {
        for (const e of es) if (e.isIntersecting) setActive(Number((e.target as HTMLElement).dataset.i));
      },
      { rootMargin: "-45% 0px -45% 0px" },
    );
    stepRefs.current.forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, [list]);

  return (
    <section ref={ref} className="act act--floor" id="floor">
      <div className="floorstory">
        <div className="floorstory__sticky">
          <div className="floorstory__viz">
            {L ? <StoryFloor L={L} step={list[active]} stepIndex={active} /> : <div className="floorstory__wait"><div className="loader"><i /><i /><i /></div></div>}
          </div>
        </div>
        <div className="floorstory__steps">
          <div className="floorstory__intro">
            <div className="eyebrow">Act three · The dance floor</div>
            <h2 className="act__title">Thousands of dancers, one floor</h2>
          </div>
          {list.map((s, i) => (
            <div key={i} data-i={i} ref={(el) => { stepRefs.current[i] = el; }} className={`step ${i === active ? "is-on" : ""}`}>
              <div className="step__card">
                <div className="step__n">{String(i + 1).padStart(2, "0")}</div>
                <h3>{s.title}</h3>
                <p>{s.text}</p>
                {s.play && entry && (
                  <a className="btn btn--primary" href={`#/stage/${entry.id}`}>
                    Open {entry.name} on the full stage <span className="arrow">→</span>
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function StoryFloor({ L, step, stepIndex }: { L: Loaded; step: Step; stepIndex: number }) {
  const T = L.res.meta.dates.length;
  const clock = useMemo(() => new Clock(T), [T]);
  const state = useMemo(() => baseState(L, "moves"), [L]);
  useEffect(() => () => clock.destroy(), [clock]);
  useEffect(() => {
    if (step.play && !prefersReducedMotion()) clock.play();
    else {
      clock.pause();
      clock.seek(0);
    }
  }, [step.play, clock]);
  const { beat } = useClockBeat(clock);
  return (
    <>
      <div className={`floorstory__floor ${stepIndex === 0 ? "is-first" : ""}`}>
        <DanceFloor
          data={L.data}
          floor={L.floor}
          hhOnly={L.hhOnly}
          clock={clock}
          state={state}
          stateVersion={0}
          selActive={false}
          trails={[]}
          emphasizeZone={step.emph}
          showZoneLabels={stepIndex >= 2}
          ariaLabel={`Dance floor of ${L.res.meta.name}`}
        />
      </div>
      <div className="floorstory__stamp">
        <span>{L.res.meta.name}</span>
        <strong>{fmtDate(L.res.meta.dates[beat])}</strong>
        <span className="dim">
          pass {beat + 1} of {T}
        </span>
      </div>
    </>
  );
}

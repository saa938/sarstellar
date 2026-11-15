// #/present: a chrome-free, deterministic ~28 s sequence for the demo video (designed at 1920x1080).
// Everything is preloaded first; then a single master clock drives every scene, so a screen
// recording always shows the same frames at the same times.
//
// Hooks for recording: window.__present = { ready, started, duration, start() }.
// ?wait=1 holds after preloading until __present.start() is called; otherwise it starts by itself.
// ?fixtures=1 lets synthetic stages fill scenes that have no real data yet (they are labeled).

import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { loadIndex, loadProof, assetUrl } from "../lib/data";
import { loadDecoded, baseState, type Loaded } from "../stage/loadDecoded";
import { Clock } from "../stage/clock";
import { DanceFloor, type TrailSpec } from "../stage/DanceFloor";
import { useClockBeat } from "../stage/Timeline";
import { fmtDate, fmtInt, fmtMonthYear } from "../lib/format";
import { MOVE_COLORS } from "../lib/moves";
import { FixtureTag } from "../components/FixtureTag";
import type { StageIndexEntry } from "../lib/types";

const Globe = lazy(() => import("../landing/Globe"));

type TrailKind = "range" | "hvdrop" | "darken" | "hhrange";

interface StageSceneDef {
  kind: "stage";
  dur: number;
  prefer: string[];
  move: string;
  caption: string;
  trails: TrailKind;
}

type SceneDef = { kind: "globe"; dur: number } | StageSceneDef | { kind: "proof"; dur: number } | { kind: "outro"; dur: number };

const PLAN: SceneDef[] = [
  { kind: "globe", dur: 3 },
  { kind: "stage", dur: 6, prefer: ["punjab"], move: "waltz", caption: "Wheat waltzes in HV. Rice bounces in HH.", trails: "range" },
  { kind: "stage", dur: 4, prefer: ["rondonia", "morton", "apui"], move: "fall", caption: "A forest falls: HV drops in one pass.", trails: "hvdrop" },
  { kind: "stage", dur: 4, prefer: ["sylhet", "indiana", "okavango"], move: "vanish", caption: "A flood makes the land vanish.", trails: "darken" },
  { kind: "stage", dur: 3, prefer: ["greenland", "jakobshavn"], move: "melt", caption: "Ice changes its face through the summer.", trails: "hhrange" },
  { kind: "proof", dur: 5 },
  { kind: "outro", dur: 3 },
];
const TOTAL = 28;

interface Scene {
  def: SceneDef;
  start: number;
  end: number;
  loaded?: Loaded;
  entry?: StageIndexEntry;
  images?: HTMLImageElement[];
}

declare global {
  interface Window {
    __present?: { ready: boolean; started: boolean; duration: number; start: () => void; t?: number };
  }
}

function pickTrails(L: Loaded, kind: TrailKind, n = 240): number[] {
  const { data, hhOnly } = L;
  const { K, T, xy } = data;
  const step = Math.max(1, Math.floor(K / 40000));
  const scored: [number, number][] = [];
  const y = (t: number, k: number) => xy[(t * K + k) * 2 + 1];
  const x = (t: number, k: number) => xy[(t * K + k) * 2];
  for (let k = 0; k < K; k += step) {
    let s = 0;
    if (kind === "range" || kind === "hhrange") {
      let lo = Infinity;
      let hi = -Infinity;
      for (let t = 0; t < T; t++) {
        const v = kind === "hhrange" && !hhOnly ? x(t, k) : y(t, k);
        lo = Math.min(lo, v);
        hi = Math.max(hi, v);
      }
      s = hi - lo;
    } else if (kind === "hvdrop") {
      s = (y(0, k) + y(Math.min(1, T - 1), k)) / 2 - (y(T - 1, k) + y(Math.max(0, T - 2), k)) / 2;
      if (y(0, k) < -16) s = -1; // only hectares that start as forest
    } else {
      let lo = Infinity;
      for (let t = 0; t < T; t++) lo = Math.min(lo, x(t, k) + y(t, k));
      s = x(0, k) + y(0, k) - lo;
    }
    scored.push([s, k]);
  }
  scored.sort((a, b) => b[0] - a[0]);
  return scored.slice(0, n).map((d) => d[1]);
}

function preloadImages(L: Loaded): Promise<HTMLImageElement[]> {
  const files = L.res.meta.images?.files ?? [];
  return Promise.all(
    files.map(
      (f) =>
        new Promise<HTMLImageElement>((resolve) => {
          const img = new Image();
          img.decoding = "async";
          img.src = assetUrl(L.res.base, f);
          img.onload = () => img.decode().then(() => resolve(img), () => resolve(img));
          img.onerror = () => resolve(img);
        }),
    ),
  );
}

export default function Present({ query }: { query: URLSearchParams }) {
  const [scenes, setScenes] = useState<Scene[] | null>(null);
  const [proof, setProof] = useState<Record<string, unknown> | null>(null);
  const [now, setNow] = useState(-1); // seconds since start, -1 = not started
  const [status, setStatus] = useState("Preparing the stages");
  const startAt = useRef(0);
  const wait = query.get("wait") === "1";
  const allowFixtures = query.get("fixtures") === "1";

  useEffect(() => {
    document.documentElement.classList.add("presenting");
    return () => document.documentElement.classList.remove("presenting");
  }, []);

  // preload everything, then build the schedule
  useEffect(() => {
    let dead = false;
    (async () => {
      const [idx, pf] = await Promise.all([loadIndex(), loadProof()]);
      const stages = idx.index.stages;
      const useFixtures = allowFixtures || idx.fixture;
      const built: { def: SceneDef; loaded?: Loaded; entry?: StageIndexEntry; images?: HTMLImageElement[] }[] = [];
      for (const def of PLAN) {
        if (def.kind === "proof" && !pf) continue;
        if (def.kind !== "stage") {
          built.push({ def });
          continue;
        }
        let entry = def.prefer.map((id) => stages.find((s) => s.id === id)).find(Boolean) ?? stages.find((s) => s.move === def.move);
        let id = entry?.id;
        if (!id && useFixtures) id = def.prefer[0];
        if (!id) continue;
        setStatus(`Loading ${entry?.name ?? id}`);
        try {
          const L = await loadDecoded(id);
          if (!entry) entry = L.res.entry;
          const images = await preloadImages(L);
          built.push({ def, loaded: L, entry, images });
        } catch {
          /* skip a scene whose data is missing */
        }
      }
      // stretch the remaining scenes to fill ~28 s
      const sum = built.reduce((a, s) => a + s.def.dur, 0);
      const k = TOTAL / Math.max(1, sum);
      let t = 0;
      const sc: Scene[] = built.map((s) => {
        const d = s.def.dur * k;
        const out = { ...s, start: t, end: t + d };
        t += d;
        return out;
      });
      if (dead) return;
      setProof(pf);
      setScenes(sc);
    })();
    return () => {
      dead = true;
    };
  }, [allowFixtures]);

  // master clock
  useEffect(() => {
    if (!scenes) return;
    let raf = 0;
    const begin = () => {
      if (window.__present?.started) return;
      window.__present!.started = true;
      startAt.current = performance.now();
      const tick = () => {
        const t = (performance.now() - startAt.current) / 1000;
        window.__present!.t = t;
        setNow(Math.min(t, TOTAL + 0.5));
        if (t < TOTAL + 0.5) raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    };
    window.__present = { ready: false, started: false, duration: TOTAL, start: begin };
    // give the GPU a moment to upload every floor before the first frame counts
    const t = setTimeout(() => {
      window.__present!.ready = true;
      if (!wait) begin();
    }, 1200);
    return () => {
      clearTimeout(t);
      cancelAnimationFrame(raf);
    };
  }, [scenes, wait]);

  const total = scenes?.length ? scenes[scenes.length - 1].end : TOTAL;
  return (
    <div className="present">
      {!scenes && (
        <div className="present__prep">
          <div className="loader">
            <i />
            <i />
            <i />
          </div>
          <p>{status}</p>
        </div>
      )}
      {scenes?.map((s, i) => {
        const p = now < 0 ? -1 : (now - s.start) / (s.end - s.start);
        const visible = now >= s.start - 0.05 && now <= s.end + 0.45;
        const fadeIn = Math.min(1, Math.max(0, (now - s.start) / 0.5));
        const fadeOut = i === scenes.length - 1 ? 1 : Math.min(1, Math.max(0, (s.end + 0.45 - now) / 0.5));
        const opacity = now < 0 ? 0 : Math.min(fadeIn, fadeOut);
        return (
          <div key={i} className="present__scene" style={{ opacity, visibility: visible || (now < 0 && i < 2) ? "visible" : "hidden" }}>
            {s.def.kind === "globe" && <GlobeScene p={p} />}
            {s.def.kind === "stage" && s.loaded && <StageScene s={s as Scene & { def: StageSceneDef; loaded: Loaded }} p={Math.max(0, Math.min(1, p))} active={visible} />}
            {s.def.kind === "proof" && proof && <ProofScene proof={proof} p={p} />}
            {s.def.kind === "outro" && <OutroScene p={p} />}
          </div>
        );
      })}
      {now >= 0 && <div className="present__progress" style={{ transform: `scaleX(${Math.min(1, now / total)})` }} />}
    </div>
  );
}

function GlobeScene({ p }: { p: number }) {
  const [stages, setStages] = useState<StageIndexEntry[]>([]);
  useEffect(() => {
    loadIndex().then((r) => setStages(r.index.stages));
  }, []);
  const show = p >= 0;
  return (
    <div className="pscene pscene--globe">
      <div className="pscene__globe">
        <Suspense fallback={null}>
          <Globe stages={stages} fill={0.4} startLng={10} lat={18} attribution={false} />
        </Suspense>
      </div>
      <div className="pscene__shade" />
      <div className={`pscene__hero ${show ? "is-on" : ""}`}>
        <h1>
          Earth is dancing.
          <br />
          <em>NISAR can see the steps.</em>
        </h1>
      </div>
      <div className="pscene__mark">
        SAR<em>stellar</em>
      </div>
    </div>
  );
}

function RadarCanvas({ images, clock }: { images: HTMLImageElement[]; clock: Clock }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const draw = (i0: number, i1: number, e: number) => {
      const r = c.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const W = Math.round(r.width * dpr);
      const H = Math.round(r.height * dpr);
      if (c.width !== W || c.height !== H) {
        c.width = W;
        c.height = H;
      }
      ctx.clearRect(0, 0, W, H);
      const put = (img: HTMLImageElement | undefined, a: number) => {
        if (!img || !img.naturalWidth || a <= 0) return;
        const s = Math.max(W / img.naturalWidth, H / img.naturalHeight);
        const w = img.naturalWidth * s;
        const h = img.naturalHeight * s;
        ctx.globalAlpha = a;
        ctx.drawImage(img, (W - w) / 2, (H - h) / 2, w, h);
      };
      put(images[i0], 1);
      if (i1 !== i0) put(images[i1], e);
      ctx.globalAlpha = 1;
    };
    return clock.subscribe((fr) => draw(Math.min(fr.i0, images.length - 1), Math.min(fr.i1, images.length - 1), fr.e));
  }, [images, clock]);
  return <canvas ref={ref} className="pscene__radar" />;
}

function StageScene({ s, p, active }: { s: Scene & { def: StageSceneDef; loaded: Loaded }; p: number; active: boolean }) {
  const L = s.loaded;
  const meta = L.res.meta;
  const T = meta.dates.length;
  const clock = useMemo(() => new Clock(T), [T]);
  const state = useMemo(() => baseState(L, "moves"), [L]);
  const trails = useMemo<TrailSpec[]>(() => {
    const ks = pickTrails(L, s.def.trails);
    return [{ name: "hl", ks, gain: Math.min(0.9, 4.5 / Math.sqrt(ks.length)), width: 1.3, tau: 2.2, future: 0.0, tint: [1, 0.84, 0.52] }];
  }, [L, s.def.trails]);
  useEffect(() => () => clock.destroy(), [clock]);
  useEffect(() => {
    if (!active) return;
    // dance through every pass in the first 82% of the scene, then hold the last pass
    clock.seek(Math.min(1, p / 0.82) * (T - 1));
  }, [p, active, clock, T]);
  const fx = !!L.res.fixture;
  const capOn = p > 0.06;
  return (
    <div className="pscene pscene--stage">
      <div className="pscene__left">
        {s.images && <RadarCanvas images={s.images} clock={clock} />}
        <div className="pscene__leftshade" />
      </div>
      <div className="pscene__floor">
        <DanceFloor data={L.data} floor={L.floor} hhOnly={L.hhOnly} clock={clock} state={state} stateVersion={0} selActive={false} trails={trails} showZoneLabels pointScale={1.15} exposure={0.8} />
      </div>
      <div className={`pscene__cap ${capOn ? "is-on" : ""}`}>
        <div className="pscene__where">
          <i style={{ background: MOVE_COLORS[s.def.move] }} />
          {meta.name}, {meta.country}
        </div>
        <h2>{s.def.caption}</h2>
        <PassTicker clock={clock} dates={meta.dates} />
      </div>
      {fx && <FixtureTag className="pscene__fixture" />}
      <div className="pscene__mark">
        SAR<em>stellar</em>
      </div>
    </div>
  );
}

function PassTicker({ clock, dates }: { clock: Clock; dates: string[] }) {
  const { beat } = useClockBeat(clock);
  return (
    <div className="pscene__ticker">
      <span className="pscene__date">{fmtDate(dates[beat])}</span>
      <span className="pscene__beats">
        {dates.map((d, i) => (
          <i key={d} className={i <= beat ? "is-on" : ""} />
        ))}
      </span>
      <span className="pscene__span">
        NISAR pass {beat + 1} of {dates.length} · {fmtMonthYear(dates[0])} to {fmtMonthYear(dates[dates.length - 1])}
      </span>
    </div>
  );
}

function ProofScene({ proof, p }: { proof: Record<string, unknown>; p: number }) {
  const h = (proof.headline ?? {}) as Record<string, number | null>;
  const s1 = (proof.sentinel1 ?? {}) as Record<string, number | null>;
  const nums: [number | null | undefined, string][] = [
    [h.reference_sites, "reference sites with independent labels"],
    [h.test_states, "states the model never saw"],
    [h.hectares_scored, "hectares scored"],
  ];
  return (
    <div className="pscene pscene--proof">
      <div className={`pscene__proof ${p > 0.03 ? "is-on" : ""}`}>
        <div className="eyebrow">How we know</div>
        {s1.ratio != null && (
          <div className="pscene__big">
            <strong>{s1.ratio.toFixed(1)}×</strong>
            <span>
              At the same detection rate, NISAR's forest-loss alerts were right {s1.ratio.toFixed(1)} times as often as Sentinel-1's
              {s1.n_sites != null ? `, across ${s1.n_sites} sites` : ""}.
            </span>
          </div>
        )}
        <div className="pscene__nums">
          {nums
            .filter(([v]) => v != null)
            .map(([v, l]) => (
              <div key={l}>
                <strong>{fmtInt(v as number)}</strong>
                <span>{l}</span>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}

function OutroScene({ p }: { p: number }) {
  return (
    <div className="pscene pscene--outro">
      <div className={`pscene__outro ${p > 0.02 ? "is-on" : ""}`}>
        <h2>Watch any place on Earth dance.</h2>
        <div className="pscene__url">sarstellar.earth</div>
        <div className="pscene__credits">NISAR L2 GCOV radar, a NASA-ISRO mission, via the ASF DAAC · Night lights: NASA GIBS</div>
      </div>
    </div>
  );
}

// #/present: a chrome-free, deterministic 28 s sequence for the demo video (designed at 1920x1080).
// Everything is preloaded first; then one master clock drives every scene, so a recording always
// shows the same frames at the same times. Real stages only.
//
// Recording hooks: window.__present = { ready, started, duration, start(), t }.
// ?wait=1 holds after preloading until __present.start() is called; otherwise it starts by itself.

import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { loadIndex, loadProof, assetUrl } from "../lib/data";
import { loadDecoded, baseState, type Loaded } from "../stage/loadDecoded";
import { Clock } from "../stage/clock";
import { DanceFloor, type TrailSpec } from "../stage/DanceFloor";
import { useClockBeat } from "../stage/useClockBeat";
import { fmtDate, fmtMonthYear, parseDate } from "../lib/format";
import { MOVE_COLORS } from "../lib/moves";
import type { StageIndexEntry } from "../lib/types";

const Globe = lazy(() => import("../landing/Globe"));

type Timing = { kind: "year" } | { kind: "jump"; date: string };

interface StageSceneDef {
  kind: "stage";
  dur: number;
  id: string;
  move: string;
  caption: string;
  sub?: string;
  timing: Timing;
}

type SceneDef = { kind: "globe"; dur: number } | StageSceneDef | { kind: "proof"; dur: number } | { kind: "outro"; dur: number };

const PLAN: SceneDef[] = [
  { kind: "globe", dur: 3 },
  { kind: "stage", dur: 6, id: "punjab", move: "waltz", caption: "Wheat waltzes in HV. Rice bounces in HH.", sub: "Same fields, two crops, two polarizations", timing: { kind: "year" } },
  { kind: "stage", dur: 4, id: "morton", move: "fall", caption: "A forest falls: HV drops in one pass.", timing: { kind: "year" } },
  { kind: "stage", dur: 4, id: "edouard", move: "bounce", caption: "Floodwater under the trees: only L-band sees it.", timing: { kind: "jump", date: "2026-09-03" } },
  { kind: "stage", dur: 3, id: "greenland", move: "melt", caption: "Ice changes its face through the summer.", timing: { kind: "year" } },
  { kind: "proof", dur: 5.5 },
  { kind: "outro", dur: 2.5 },
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

function nearestIndex(dates: string[], d: string) {
  const t = parseDate(d);
  let best = 0;
  let bd = Infinity;
  dates.forEach((x, i) => {
    const dd = Math.abs(parseDate(x) - t);
    if (dd < bd) {
      bd = dd;
      best = i;
    }
  });
  return best;
}

/** Hectares whose dance best shows the scene's move, for gold-free, move-colored trails. */
function pickTrails(L: Loaded, def: StageSceneDef): number[] {
  const { data, hhOnly } = L;
  const { K, T, xy } = data;
  const ids = L.res.meta.moves?.ids ?? [];
  const mi = (id: string) => ids.indexOf(id);
  const X = (t: number, k: number) => xy[(t * K + k) * 2];
  const Y = (t: number, k: number) => xy[(t * K + k) * 2 + 1];
  const top = (score: (k: number) => number, n: number, filter?: (k: number) => boolean) => {
    const out: [number, number][] = [];
    const step = Math.max(1, Math.floor(K / 60000));
    for (let k = 0; k < K; k += step) {
      if (filter && !filter(k)) continue;
      out.push([score(k), k]);
    }
    out.sort((a, b) => b[0] - a[0]);
    return out.slice(0, n).map((d) => d[1]);
  };
  const isMove = (id: string) => (k: number) => !data.move || data.move[k] === mi(id);
  const range = (k: number, f: (t: number, k: number) => number) => {
    let lo = Infinity;
    let hi = -Infinity;
    for (let t = 0; t < T; t++) {
      const v = f(t, k);
      lo = Math.min(lo, v);
      hi = Math.max(hi, v);
    }
    return hi - lo;
  };
  if (def.id === "punjab" || def.move === "waltz") {
    return [...top((k) => range(k, Y), 130, isMove("waltz")), ...top((k) => range(k, X), 110, isMove("bounce"))];
  }
  if (def.move === "fall") return top((k) => (Y(0, k) + Y(1, k)) / 2 - (Y(T - 1, k) + Y(T - 2, k)) / 2, 220, isMove("fall"));
  if (def.timing.kind === "jump") {
    const j = nearestIndex(L.res.meta.dates, def.timing.date);
    const i = Math.max(0, j - 1);
    return top((k) => X(j, k) - X(i, k) - Math.abs(Y(j, k) - Y(i, k)), 220, isMove("bounce"));
  }
  return top((k) => range(k, hhOnly ? Y : X), 160, isMove(def.move));
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
  const [now, setNow] = useState(-1);
  const [status, setStatus] = useState("Preparing the stages");
  const startAt = useRef(0);
  const wait = query.get("wait") === "1";

  useEffect(() => {
    document.documentElement.classList.add("presenting");
    return () => document.documentElement.classList.remove("presenting");
  }, []);

  useEffect(() => {
    let dead = false;
    (async () => {
      const [idx, pf] = await Promise.all([loadIndex(), loadProof()]);
      const stages = idx.index.stages;
      const built: { def: SceneDef; loaded?: Loaded; entry?: StageIndexEntry; images?: HTMLImageElement[] }[] = [];
      for (const def of PLAN) {
        if (def.kind === "proof" && !pf) continue;
        if (def.kind !== "stage") {
          built.push({ def });
          continue;
        }
        const entry = stages.find((s) => s.id === def.id);
        if (!entry || idx.fixture) continue; // real stages only
        setStatus(`Loading ${entry.name}`);
        try {
          const L = await loadDecoded(entry.id);
          if (L.res.fixture) continue;
          const images = await preloadImages(L);
          built.push({ def, loaded: L, entry, images });
        } catch {
          /* skip a scene whose data is missing */
        }
      }
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
  }, []);

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
    const t = setTimeout(() => {
      window.__present!.ready = true;
      if (!wait) begin();
    }, 1500);
    return () => {
      clearTimeout(t);
      cancelAnimationFrame(raf);
    };
  }, [scenes, wait]);

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
        const fadeIn = i === 0 ? Math.min(1, Math.max(0, now / 0.8)) : Math.min(1, Math.max(0, (now - s.start) / 0.45));
        const fadeOut = i === scenes.length - 1 ? 1 : Math.min(1, Math.max(0, (s.end + 0.45 - now) / 0.45));
        const opacity = now < 0 ? 0 : Math.min(fadeIn, fadeOut);
        return (
          <div key={i} className="present__scene" style={{ opacity, visibility: visible || (now < 0 && i < 2) ? "visible" : "hidden", zIndex: i }}>
            {s.def.kind === "globe" && <GlobeScene p={p} />}
            {s.def.kind === "stage" && s.loaded && <StageScene s={s as Scene & { def: StageSceneDef; loaded: Loaded }} p={Math.max(0, Math.min(1, p))} active={visible} />}
            {s.def.kind === "proof" && proof && <ProofScene proof={proof} p={p} />}
            {s.def.kind === "outro" && <OutroScene p={p} />}
          </div>
        );
      })}
    </div>
  );
}

function GlobeScene({ p }: { p: number }) {
  const [stages, setStages] = useState<StageIndexEntry[]>([]);
  useEffect(() => {
    loadIndex().then((r) => setStages(r.index.stages));
  }, []);
  return (
    <div className="pscene pscene--globe">
      <div className="pscene__globe">
        <Suspense fallback={null}>
          <Globe stages={stages} fill={0.4} startLng={-28} lat={22} attribution={false} />
        </Suspense>
      </div>
      <div className="pscene__shade" />
      <div className={`pscene__hero ${p >= 0.04 ? "is-on" : ""}`}>
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
    const ks = pickTrails(L, s.def);
    return [{ name: "hl", ks, gain: Math.min(0.85, 5 / Math.sqrt(Math.max(1, ks.length))), width: 1.4, tau: 2.4, future: 0, tint: null }];
  }, [L, s.def]);
  const jumpTo = s.def.timing.kind === "jump" ? nearestIndex(meta.dates, s.def.timing.date) : -1;
  useEffect(() => () => clock.destroy(), [clock]);
  useEffect(() => {
    if (!active) return;
    if (jumpTo >= 0) {
      // hold the pass before, step onto the storm pass, then hold it
      const from = Math.max(0, jumpTo - 1);
      clock.seek(from + Math.min(1, Math.max(0, (p - 0.16) / 0.26)));
    } else {
      // dance through every pass in the first 85% of the scene, then hold the last pass
      clock.seek(Math.min(1, p / 0.85) * (T - 1));
    }
  }, [p, active, clock, T, jumpTo]);
  return (
    <div className="pscene pscene--stage">
      <div className="pscene__left">
        {s.images && <RadarCanvas images={s.images} clock={clock} />}
        <div className="pscene__leftshade" />
      </div>
      <div className="pscene__floor">
        <DanceFloor data={L.data} floor={L.floor} hhOnly={L.hhOnly} clock={clock} state={state} stateVersion={0} selActive={false} trails={trails} showZoneLabels pointScale={1.15} exposure={0.8} />
      </div>
      <div className={`pscene__cap ${p > 0.05 ? "is-on" : ""}`}>
        <div className="pscene__where">
          <i style={{ background: MOVE_COLORS[s.def.move], color: MOVE_COLORS[s.def.move] }} />
          {meta.name}, {meta.country}
        </div>
        <h2>{s.def.caption}</h2>
        {s.def.sub && <p className="pscene__sub">{s.def.sub}</p>}
        <PassTicker clock={clock} dates={meta.dates} />
      </div>
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

/** "6×" for big ratios, "7.8×" below 10 when the decimal matters. */
function times(r: number) {
  if (!Number.isFinite(r)) return "";
  if (r >= 10) return `${Math.round(r)}×`;
  const one = Math.round(r * 10) / 10;
  return Number.isInteger(one) ? `${one}×` : `${one.toFixed(1)}×`;
}

function ProofScene({ proof, p }: { proof: Record<string, unknown>; p: number }) {
  const h = (proof.headline ?? {}) as Record<string, number | null>;
  const s1 = (proof.sentinel1 ?? {}) as Record<string, number | null>;
  const pol = proof.polarization as { variants?: { name: string; auprc?: Record<string, number | null> }[] } | undefined;
  const hv = pol?.variants?.find((v) => /^HV only/i.test(v.name))?.auprc?.fall;
  const hh = pol?.variants?.find((v) => /^HH only/i.test(v.name))?.auprc?.fall;
  const items: { big: string; text: string; foot: string }[] = [];
  if (hv != null && hh != null && hh > 0) {
    const r = hv / hh;
    items.push({ big: `${Math.round(r)}×`, text: `Forest loss is an HV move: HV alone finds it ${Math.round(r)}× better than HH alone.`, foot: `AUPRC ${hv.toFixed(2)} vs ${hh.toFixed(3)}, held-out states` });
  }
  if (s1.ratio != null) {
    items.push({ big: times(s1.ratio), text: `NISAR's forest-loss alerts were ${times(s1.ratio)} more often real than Sentinel-1's.`, foot: `same detection rate${s1.n_sites != null ? `, ${s1.n_sites} sites` : ""}` });
  }
  if (h.train_sites != null && h.test_states != null) {
    items.push({ big: `${h.train_sites}`, text: `Learned on ${h.train_sites} US reference sites, tested on ${h.test_states} states it never saw.`, foot: `independent reference labels, ${h.reference_sites ?? h.train_sites} sites in all` });
  }
  return (
    <div className="pscene pscene--proof">
      <div className="pscene__proof">
        <div className={`eyebrow ${p > 0.02 ? "is-on" : ""}`}>Measured, not imagined</div>
        <div className="pscene__claims">
          {items.map((it, i) => (
            <div key={i} className={`pscene__claim ${p > 0.04 + i * 0.16 ? "is-on" : ""}`}>
              <strong>{it.big}</strong>
              <span>{it.text}</span>
              <em>{it.foot}</em>
            </div>
          ))}
        </div>
      </div>
      <div className="pscene__mark">
        SAR<em>stellar</em>
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
        <div className="pscene__credits">NISAR radar data: NASA-ISRO, via the ASF DAAC · Night lights: NASA GIBS</div>
      </div>
    </div>
  );
}

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Nav } from "../components/Nav";
import { FixtureTag } from "../components/FixtureTag";
import { assetUrl, loadIndex, loadMoves, loadStage, type IndexResult, type MovesResult, type StageResult } from "../lib/data";
import { DEFAULT_FLOOR, MOVE_COLORS, MOVE_NAMES, ZONE_STARLIGHT, hexToRgb, lighten } from "../lib/moves";
import { decodeStage, type DecodeResult } from "../stage/decoded";
import { Clock, prefersReducedMotion } from "../stage/clock";
import { DanceFloor, type BrushTool, type TrailSpec } from "../stage/DanceFloor";
import { StageMap, type Basemap } from "../stage/StageMap";
import { Timeline, useClockBeat, type Score } from "../stage/Timeline";
import { SoloCard } from "../stage/SoloCard";
import { signal } from "../lib/signal";
import { fmtDate, fmtInt, parseDate } from "../lib/format";
import type { FloorSpec, StageMeta, StoryBeat } from "../lib/types";

type Loaded = {
  res: StageResult;
  moves: MovesResult | null;
  index: IndexResult;
  data: DecodeResult;
  floor: FloorSpec;
  hhOnly: boolean;
};

export default function StagePage({ id, query }: { id: string; query: URLSearchParams }) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState("Finding the stage");
  const [index, setIndex] = useState<IndexResult | null>(null);

  useEffect(() => {
    loadIndex().then(setIndex);
  }, []);

  useEffect(() => {
    let dead = false;
    setLoaded(null);
    setError(null);
    setStep("Finding the stage");
    (async () => {
      const [res, moves, idx] = await Promise.all([loadStage(id), loadMoves(), loadIndex()]);
      if (dead) return;
      if (!res) {
        setError(`There is no stage called "${id}" yet.`);
        return;
      }
      const meta = res.meta;
      const floor = moves?.doc.floor ?? DEFAULT_FLOOR;
      const P = meta.blocks.pols.length;
      const hhOnly = P === 1 || !meta.blocks.pols.includes("HV");
      setStep(`Reading ${fmtInt(meta.grid.nx * meta.grid.ny)} hectares across ${meta.dates.length} passes`);
      const zoneTints: Record<string, [number, number, number]> = {};
      for (const [k, v] of Object.entries(ZONE_STARLIGHT)) zoneTints[k] = hexToRgb(v);
      try {
        const data = await decodeStage({
          url: assetUrl(res.base, meta.blocks.file),
          movesUrl: meta.moves ? assetUrl(res.base, meta.moves.file) : null,
          nMoves: meta.moves?.ids.length ?? 0,
          T: meta.dates.length,
          P,
          nx: meta.grid.nx,
          ny: meta.grid.ny,
          scale: meta.blocks.scale,
          offset: meta.blocks.offset,
          nodata: meta.blocks.nodata,
          corners: meta.corners,
          zones: floor.zones.map((z) => ({ id: z.id, center: z.center })),
          zoneTints,
          hhOnly,
        });
        if (dead) return;
        setLoaded({ res, moves, index: idx, data, floor, hhOnly });
      } catch (e) {
        if (!dead) setError(String((e as Error).message || e));
      }
    })();
    return () => {
      dead = true;
    };
  }, [id]);

  const stages = index?.index.stages ?? [];
  return (
    <div className="stage-page">
      <Nav active="explore">
        <div className="stage-switch" role="navigation" aria-label="Stages">
          {stages.map((s) => (
            <a key={s.id} href={`#/stage/${s.id}`} className={s.id === id ? "is-on" : ""}>
              {s.name}
            </a>
          ))}
        </div>
      </Nav>
      {loaded ? (
        <StageView key={id} loaded={loaded} query={query} />
      ) : (
        <div className="stage-loading">
          {error ? (
            <div className="stage-loading__msg">
              <div className="eyebrow">Stage unavailable</div>
              <p>{error}</p>
              <a className="btn" href="#/explore">
                See all stages
              </a>
            </div>
          ) : (
            <div className="stage-loading__msg">
              <div className="loader" aria-hidden>
                <i />
                <i />
                <i />
              </div>
              <p>{step}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
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

function StageView({ loaded, query }: { loaded: Loaded; query: URLSearchParams }) {
  const { res, moves, data, floor, hhOnly } = loaded;
  const meta = res.meta;
  const T = meta.dates.length;
  const clock = useMemo(() => new Clock(T), [T]);
  const hover = useMemo(() => signal(-1), []);
  const [solo, setSolo] = useState<number | null>(null);
  const [sel, setSel] = useState<{ mask: Uint8Array | null; count: number; v: number }>({ mask: null, count: 0, v: 0 });
  const [tool, setTool] = useState<BrushTool>(() => (window.matchMedia?.("(pointer: coarse)").matches ? "none" : "rect"));
  const [boxTool, setBoxTool] = useState(false);
  const [basemap, setBasemap] = useState<Basemap>("dark");
  const [radarOn, setRadarOn] = useState(true);
  const hasMoves = !!(data.move && meta.moves);
  const [colorMode, setColorMode] = useState<"moves" | "zone">(hasMoves ? "moves" : "zone");
  const [showMoves, setShowMoves] = useState(hasMoves);
  const moveIds = meta.moves?.ids ?? null;
  const moveDefs = moves?.doc.moves ?? [];

  const storyBeats = useMemo(() => {
    const b = meta.story?.beats ?? [];
    return b.map((beat: StoryBeat) => ({ index: nearestIndex(meta.dates, beat.date), beat })).sort((a, b2) => a.index - b2.index);
  }, [meta]);

  useEffect(() => {
    clock.holdBeats = new Set(storyBeats.map((b) => b.index));
  }, [clock, storyBeats]);

  // initial time and autoplay
  useEffect(() => {
    const t0 = Number(query.get("t"));
    if (Number.isFinite(t0) && query.get("t") != null) clock.seek(t0);
    const auto = query.get("play") !== "0" && !prefersReducedMotion();
    const timer = auto ? window.setTimeout(() => clock.play(), 700) : 0;
    return () => {
      window.clearTimeout(timer);
      clock.destroy();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clock]);

  // solo from the URL (for sharing a hectare)
  useEffect(() => {
    const n = Number(query.get("block"));
    if (query.get("block") != null && Number.isFinite(n) && data.nToK[n] >= 0) setSolo(data.nToK[n]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const moveRGB = useMemo(() => (moveIds ? moveIds.map((m) => hexToRgb(MOVE_COLORS[m] || "#999999")) : null), [moveIds]);
  const moveRGBDot = useMemo(() => (moveRGB ? moveRGB.map((c) => lighten(c, 0.18)) : null), [moveRGB]);

  const hlKs = useMemo(() => {
    const hl = meta.story?.highlight?.blocks ?? [];
    return hl.map((n) => data.nToK[n]).filter((k) => k != null && k >= 0);
  }, [meta, data]);

  const state = useMemo(() => {
    const K = data.K;
    const out = new Uint8Array(K * 4);
    const useMoves = colorMode === "moves" && data.move && moveRGBDot;
    const hlSet = sel.mask ? null : new Set(hlKs);
    for (let k = 0; k < K; k++) {
      let r = data.tint[k * 3];
      let g = data.tint[k * 3 + 1];
      let b = data.tint[k * 3 + 2];
      if (useMoves) {
        const m = data.move![k];
        if (m > 0 && m < moveRGBDot!.length) {
          [r, g, b] = moveRGBDot![m];
        } else {
          r *= 0.78;
          g *= 0.78;
          b *= 0.82;
        }
      }
      let f = 0;
      if (sel.mask && sel.mask[k]) f |= 1;
      if (hlSet && hlSet.has(k)) f |= 2;
      out[k * 4] = r;
      out[k * 4 + 1] = g;
      out[k * 4 + 2] = b;
      out[k * 4 + 3] = f;
    }
    return out;
  }, [data, colorMode, moveRGBDot, sel, hlKs]);

  const trails = useMemo(() => {
    const list: TrailSpec[] = [];
    if (sel.mask && sel.count > 0) {
      const ks: number[] = [];
      const stride = Math.max(1, Math.floor(sel.count / 420));
      let seen = 0;
      for (let k = 0; k < data.K && ks.length < 420; k++) {
        if (!sel.mask[k]) continue;
        if (seen++ % stride === 0) ks.push(k);
      }
      list.push({ name: "sel", ks, gain: Math.min(0.9, Math.max(0.1, 2.4 / Math.sqrt(ks.length))), width: 1.15, tau: 2.6, future: 0.05 });
    } else if (hlKs.length) {
      list.push({ name: "hl", ks: hlKs, gain: 0.95, width: 1.6, tau: 4.5, future: 0.14 });
    }
    if (solo != null) list.push({ name: "solo", ks: [solo], gain: 1.8, width: 2.4, tau: 8, future: 0.22, tint: [1, 0.86, 0.55] });
    return list;
  }, [sel, hlKs, solo, data]);

  const onSelect = useCallback((mask: Uint8Array | null, count: number) => {
    setSel((s) => ({ mask, count, v: s.v + 1 }));
  }, []);
  const clearAll = useCallback(() => {
    setSel((s) => ({ mask: null, count: 0, v: s.v + 1 }));
    setSolo(null);
  }, []);
  const selectMove = (mi: number) => {
    if (!data.move) return;
    const mask = new Uint8Array(data.K);
    let c = 0;
    for (let k = 0; k < data.K; k++)
      if (data.move[k] === mi) {
        mask[k] = 1;
        c++;
      }
    setSel((s) => ({ mask: c ? mask : null, count: c, v: s.v + 1 }));
  };

  // keyboard
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const tgt = e.target as HTMLElement;
      if (tgt.closest("input, textarea, select")) return;
      if (e.code === "Space") {
        if (tgt.closest("button, a")) return;
        e.preventDefault();
        clock.toggle();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        clock.step(1);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        clock.step(-1);
      } else if (e.key === "Escape") {
        clearAll();
        setBoxTool(false);
      }
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [clock, clearAll]);

  const score = useMemo<Score | null>(() => {
    if (!data.beat || !moveIds) return null;
    const M = moveIds.length;
    const frac = new Float32Array(T * M);
    for (let t = 0; t < T; t++) {
      const o = t * data.K;
      for (let k = 0; k < data.K; k++) {
        const m = data.beat[o + k];
        if (m > 0 && m < M) frac[t * M + m]++;
      }
      for (let m = 0; m < M; m++) frac[t * M + m] /= data.K;
    }
    return { frac, M, colors: moveIds.map((m) => MOVE_COLORS[m] ?? "#999"), names: moveIds.map((m) => MOVE_NAMES[m] ?? m) };
  }, [data, moveIds, T]);

  const km2 = sel.count * (meta.grid.res_m * meta.grid.res_m) / 1e6;
  const moveCounts = data.moveCounts;

  return (
    <main className={`stage ${solo != null ? "has-solo" : ""}`}>
      <section className="stage__map" aria-label="Map">
        <StageMap
          meta={meta}
          base={res.base}
          data={data}
          clock={clock}
          hover={hover}
          solo={solo}
          selection={sel.mask}
          selVersion={sel.v}
          basemap={basemap}
          showMoves={showMoves && colorMode === "moves"}
          moveColors={moveRGB}
          boxTool={boxTool}
          onPick={(k) => setSolo(k)}
          onSelect={onSelect}
          onBoxDone={() => setBoxTool(false)}
          radarOn={radarOn}
        />
        <StoryCard meta={meta} fixture={res.fixture} />
        <div className="maptools" role="toolbar" aria-label="Map tools">
          <div className="seg seg--sm">
            <button className={basemap === "dark" ? "is-on" : ""} onClick={() => setBasemap("dark")}>
              Dark
            </button>
            <button className={basemap === "satellite" ? "is-on" : ""} onClick={() => setBasemap("satellite")}>
              Satellite
            </button>
          </div>
          <button className={`chip ${radarOn ? "is-on" : ""}`} onClick={() => setRadarOn((v) => !v)} aria-pressed={radarOn}>
            <span className="chip__dot chip__dot--radar" /> Radar image
          </button>
          {hasMoves && (
            <button className={`chip ${showMoves && colorMode === "moves" ? "is-on" : ""}`} onClick={() => { setShowMoves((v) => !v); setColorMode("moves"); }} aria-pressed={showMoves}>
              <span className="chip__dot chip__dot--moves" /> Moves on map
            </button>
          )}
          <button className={`chip ${boxTool ? "is-on" : ""}`} onClick={() => setBoxTool((v) => !v)} aria-pressed={boxTool} title="Draw a box on the map to light up those hectares on the floor">
            <svg viewBox="0 0 16 16" width="13" height="13" aria-hidden>
              <rect x="2" y="2" width="12" height="12" rx="1.5" stroke="currentColor" strokeDasharray="2.5 2" fill="none" />
            </svg>
            {boxTool ? "Drag on the map" : "Select an area"}
          </button>
        </div>
        <CaptionToast clock={clock} beats={storyBeats} />
        <MapKey clock={clock} dates={meta.dates} hhOnly={hhOnly} hasImages={!!meta.images?.files?.length} />
        {res.fixture && <FixtureTag className="stage__fixture" />}
        {solo != null && (
          <SoloCard
            data={data}
            k={solo}
            dates={meta.dates}
            nx={meta.grid.nx}
            clock={clock}
            zones={floor.zones}
            hhOnly={hhOnly}
            moveIds={moveIds}
            moves={moveDefs}
            fixture={res.fixture}
            onClose={() => setSolo(null)}
          />
        )}
      </section>

      <section className="stage__floor" aria-label="Dance floor">
        <div className="floorhead">
          <div className="floorhead__title">
            <h2>The dance floor</h2>
            <p>
              Every dot is one hectare, placed by its two echoes. <span className="hide-sm">Drag to select, click a dot to follow it.</span>
            </p>
          </div>
          <div className="floorhead__tools">
            <div className="seg seg--sm" role="group" aria-label="Selection tool">
              {window.matchMedia?.("(pointer: coarse)").matches && (
                <button className={tool === "none" ? "is-on" : ""} onClick={() => setTool("none")}>
                  Tap
                </button>
              )}
              <button className={tool === "rect" ? "is-on" : ""} onClick={() => setTool("rect")} title="Drag a rectangle on the floor">
                Box
              </button>
              <button className={tool === "lasso" ? "is-on" : ""} onClick={() => setTool("lasso")} title="Draw a free shape on the floor">
                Lasso
              </button>
            </div>
          </div>
        </div>
        <div className="floorhead__status">
          {sel.count > 0 ? (
            <span className="selchip">
              <strong>{fmtInt(sel.count)}</strong> hectares selected <span className="dim">· {km2 < 10 ? km2.toFixed(2) : fmtInt(km2)} km²</span>
              <button onClick={() => setSel((s) => ({ mask: null, count: 0, v: s.v + 1 }))}>Clear</button>
            </span>
          ) : hlKs.length && meta.story?.highlight?.label ? (
            <span className="dim">
              <span className="trail-key" /> Trails: {meta.story.highlight.label}
            </span>
          ) : (
            <span className="dim">{fmtInt(data.K)} hectares on the floor</span>
          )}
        </div>
        <div className="stage__floorbox">
          <DanceFloor
            data={data}
            floor={floor}
            hhOnly={hhOnly}
            clock={clock}
            state={state}
            stateVersion={sel.v}
            selActive={!!sel.mask}
            trails={trails}
            hover={hover}
            solo={solo}
            tool={tool}
            onSelect={onSelect}
            onPick={(k) => setSolo(k)}
          />
        </div>
        <FloorLegend
          hasMoves={hasMoves}
          colorMode={colorMode}
          setColorMode={setColorMode}
          moveIds={moveIds}
          counts={moveCounts}
          onPickMove={selectMove}
          zones={floor.zones}
          hhOnly={hhOnly}
        />
      </section>

      <section className="stage__time" aria-label="Timeline">
        <Timeline dates={meta.dates} clock={clock} beats={storyBeats} score={score} />
      </section>
    </main>
  );
}

function StoryCard({ meta, fixture }: { meta: StageMeta; fixture: boolean }) {
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const story = meta.story ?? {};
  const s = meta.stack;
  const pols = (s.pols ?? meta.blocks.pols).join(" + ");
  if (collapsed)
    return (
      <button className="storycard storycard--min" onClick={() => setCollapsed(false)}>
        <span className="eyebrow">{meta.name}</span> {story.title ?? meta.name} <span className="dim">· Story</span>
      </button>
    );
  return (
    <article className="storycard">
      <div className="storycard__top">
        <div className="eyebrow">
          {meta.name}, {meta.country}
        </div>
        <button className="btn-icon btn-icon--sm" onClick={() => setCollapsed(true)} aria-label="Minimize story">
          <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden>
            <path d="M6 12h12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </button>
      </div>
      <h1 className="storycard__title">{story.title ?? meta.name}</h1>
      {story.lede && <p className="storycard__lede">{story.lede}</p>}
      {open && (story.body ?? []).map((p, i) => <p key={i} className="storycard__body">{p}</p>)}
      {open && (
        <>
          <dl className="storycard__meta">
            <div>
              <dt>Passes</dt>
              <dd>{meta.dates.length}</dd>
            </div>
            <div>
              <dt>Dates</dt>
              <dd>
                {fmtDate(meta.dates[0])} to {fmtDate(meta.dates[meta.dates.length - 1])}
              </dd>
            </div>
            <div>
              <dt>Track</dt>
              <dd>
                {s.track ?? "?"} {s.direction === "A" ? "ascending" : s.direction === "D" ? "descending" : ""}
              </dd>
            </div>
            <div>
              <dt>Mode</dt>
              <dd>
                {s.mode ?? "?"}
                {s.bandwidth_mhz ? `, ${s.bandwidth_mhz} MHz` : ""}
              </dd>
            </div>
            <div>
              <dt>Polarizations</dt>
              <dd>{pols}</dd>
            </div>
            <div>
              <dt>Area</dt>
              <dd>
                {meta.stats?.valid_blocks ? `${fmtInt(meta.stats.valid_blocks)} ha` : ""}
                {meta.stats?.km2 ? ` · ${fmtInt(meta.stats.km2)} km²` : ""}
              </dd>
            </div>
          </dl>
          {meta.sources?.length ? (
            <div className="storycard__sources">
              <div className="eyebrow">Sources</div>
              <ul>
                {meta.sources.map((src) => (
                  <li key={src.name}>{src.url ? <a href={src.url} target="_blank" rel="noreferrer">{src.name}</a> : src.name}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {fixture && <p className="storycard__note">This stage uses synthetic preview data while the NISAR bundles are prepared.</p>}
        </>
      )}
      <button className="linkbtn" onClick={() => setOpen((v) => !v)}>
        {open ? "Less" : "Read the story and data details"}
      </button>
    </article>
  );
}

function CaptionToast({ clock, beats }: { clock: Clock; beats: { index: number; beat: StoryBeat }[] }) {
  const { beat } = useClockBeat(clock);
  const cur = beats.filter((b) => b.index <= beat).pop();
  const show = cur && beat - cur.index <= 2;
  const last = useRef(cur);
  if (show) last.current = cur;
  return (
    <div className={`caption ${show ? "is-on" : ""}`} aria-hidden={!show}>
      {last.current && (
        <>
          <span className="caption__date">{fmtDate(last.current.beat.date)}</span>
          <span className="caption__text">{last.current.beat.caption}</span>
        </>
      )}
    </div>
  );
}

function MapKey({ clock, dates, hhOnly, hasImages }: { clock: Clock; dates: string[]; hhOnly: boolean; hasImages: boolean }) {
  const { beat } = useClockBeat(clock);
  return (
    <div className="mapkey">
      <div className="mapkey__stamp">
        <span className="mapkey__label">NISAR pass</span> <strong>{fmtDate(dates[beat])}</strong>
      </div>
      {hasImages && (
        <div className="mapkey__legend">
          {hhOnly ? (
            <>
              <span className="mapkey__rgb">
                <i className="mapkey__ramp" /> HH brightness, quiet to loud
              </span>
              <span className="mapkey__hint">Over ice NISAR listens with HH only</span>
            </>
          ) : (
            <>
              <span className="mapkey__rgb">
                <i style={{ background: "#e0645f" }} />R HH <i style={{ background: "#5ad07a" }} />G HV <i style={{ background: "#6a7bff" }} />B HH
              </span>
              <span className="mapkey__hint">
                <i style={{ background: "#3f9a3a" }} />vegetation <i style={{ background: "#e9a6d6" }} />double bounce <i style={{ background: "#000", border: "1px solid #444" }} />water
              </span>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function FloorLegend(props: {
  hasMoves: boolean;
  colorMode: "moves" | "zone";
  setColorMode: (m: "moves" | "zone") => void;
  moveIds: string[] | null;
  counts: number[] | null;
  onPickMove: (i: number) => void;
  zones: FloorSpec["zones"];
  hhOnly: boolean;
}) {
  const { hasMoves, colorMode, setColorMode, moveIds, counts, onPickMove, zones, hhOnly } = props;
  return (
    <div className="legend">
      {hasMoves && (
        <div className="seg seg--sm legend__mode" role="group" aria-label="Color dots by">
          <button className={colorMode === "moves" ? "is-on" : ""} onClick={() => setColorMode("moves")}>
            Color by move
          </button>
          <button className={colorMode === "zone" ? "is-on" : ""} onClick={() => setColorMode("zone")}>
            by starting surface
          </button>
        </div>
      )}
      {hasMoves && colorMode === "moves" && moveIds && counts ? (
        <div className="legend__items">
          {moveIds.map((m, i) =>
            counts[i] ? (
              <button key={m} className="legend__item" onClick={() => onPickMove(i)} title={`Select every hectare doing ${MOVE_NAMES[m] ?? m}`}>
                <span className="swatch" style={{ background: m === "still" ? "#b9b6ab" : MOVE_COLORS[m] }} />
                {MOVE_NAMES[m] ?? m}
                <span className="legend__n">{fmtInt(counts[i])}</span>
              </button>
            ) : null,
          )}
        </div>
      ) : hhOnly ? (
        <div className="legend__items">
          <span className="legend__note">One partner: over ice NISAR listens with HH only. Each dot keeps its first-pass HH across and rises or sinks as its surface gets louder or quieter.</span>
        </div>
      ) : (
        <div className="legend__items">
          <span className="legend__note">Dots are tinted by where each hectare started:</span>
          {zones.map((z) => (
            <span key={z.id} className="legend__item legend__item--static">
              <span className="swatch" style={{ background: ZONE_STARLIGHT[z.id] ?? "#ddd" }} />
              {z.label.split(":")[0]}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

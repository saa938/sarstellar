import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Nav } from "../components/Nav";
import { Footer } from "../components/Footer";
import { assetUrl, loadIndex, type IndexResult } from "../lib/data";
import { loadDecoded, type Loaded } from "../stage/loadDecoded";
import { Clock } from "../stage/clock";
import { useClockBeat } from "../stage/useClockBeat";
import { PlaceChart } from "../chart/PlaceChart";
import { CHANGE_COLOR, CHANGE_LABEL, CHANGE_NOTE } from "../lib/labels";
import { fmtDate, fmtDb, fmtInt, fmtMonthYear, parseDate } from "../lib/format";
import { formatLonLat } from "../lib/geo";
import { useReveal } from "./Story";

// maplibre is heavy and the single-place page shares this module, so the map loads on its own
const PlacesMap = lazy(() => import("./PlacesMap"));

// ---------------------------------------------------------------- grid

export function PlacesGrid() {
  const [idx, setIdx] = useState<IndexResult | null>(null);
  // the card the pointer or keyboard is on: the map highlights it and flies there
  const [active, setActive] = useState<string | null>(null);
  useEffect(() => {
    loadIndex().then(setIdx);
  }, []);
  const stages = idx?.index.stages ?? [];
  const pick = (id: string) => ({
    onMouseEnter: () => setActive(id),
    onFocus: () => setActive(id),
    onMouseLeave: () => setActive(null),
    onBlur: () => setActive(null),
  });
  return (
    <div className="page">
      <Nav active="places" />
      <header className="page__head">
        <div className="eyebrow">Places</div>
        <h1 className="sec__title">{stages.length || 9} places NISAR watched</h1>
        <p className="sec__lede" style={{ maxWidth: 720 }}>
          Each place is a real stack of NISAR radar passes, one every 12 days. Open one to watch it change, and see every hectare move by its two echoes.
        </p>
      </header>
      <div className="page__body">
        {stages.length > 0 && (
          <Suspense fallback={null}>
            <PlacesMap stages={stages} activeId={active} onOpen={(id) => (window.location.hash = `#/places/${id}`)} />
          </Suspense>
        )}
        <div className="placegrid">
          {stages.map((s) => (
            <a key={s.id} className="placecard" href={`#/places/${s.id}`} {...pick(s.id)}>
              <div className="placecard__img">
                <img src={assetUrl(idx!.base, s.thumb)} alt={`NISAR radar image of ${s.name}`} loading="lazy" decoding="async" />
              </div>
              <div className="placecard__body">
                <div className="eyebrow">
                  {s.name} · {s.country}
                </div>
                <h2>{s.title}</h2>
                <p>{s.teaser}</p>
                <div className="placecard__meta">
                  {s.n_passes} passes · {fmtMonthYear(s.first)} to {fmtMonthYear(s.last)}
                </div>
              </div>
            </a>
          ))}
        </div>
      </div>
      <Footer />
    </div>
  );
}

// ---------------------------------------------------------------- one place

export function Place({ id }: { id: string }) {
  const [L, setL] = useState<Loaded | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let dead = false;
    setL(null);
    setErr(null);
    loadDecoded(id)
      .then((x) => !dead && setL(x))
      .catch((e) => !dead && setErr(String((e as Error).message || e)));
    return () => {
      dead = true;
    };
  }, [id]);
  return (
    <div className="page">
      <Nav active="places" />
      {L ? (
        <PlaceView key={id} L={L} />
      ) : (
        <div className="page__head">
          <a className="linkbtn" href="#/places">
            ← All places
          </a>
          {err ? (
            <p className="sec__lede" style={{ marginTop: 20 }}>
              {err}
            </p>
          ) : (
            <div className="placeload">
              <div className="loader">
                <i />
                <i />
                <i />
              </div>
              <p className="dim">Reading every pass</p>
            </div>
          )}
        </div>
      )}
      <Footer />
    </div>
  );
}

function PlaceView({ L }: { L: Loaded }) {
  const meta = L.res.meta;
  const { data } = L;
  const T = meta.dates.length;
  const clock = useMemo(() => new Clock(T), [T]);
  const [selected, setSelected] = useState<number | null>(null);
  const moveIds = meta.moves?.ids ?? null;

  useEffect(() => {
    clock.setTempo("slow");
    const t = window.setTimeout(() => {
      if (!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) clock.play();
    }, 900);
    return () => {
      clearTimeout(t);
      clock.destroy();
    };
  }, [clock]);

  const paths = useMemo(() => {
    const hl = meta.story?.highlight?.blocks ?? [];
    return hl.map((n) => data.nToK[n]).filter((k) => k != null && k >= 0).slice(0, 6);
  }, [meta, data]);

  const sample = useMemo(() => {
    const max = 8000;
    if (data.K <= max) return Int32Array.from({ length: data.K }, (_, i) => i);
    const out = new Int32Array(max);
    const stride = data.K / max;
    for (let i = 0; i < max; i++) out[i] = Math.floor(i * stride + (((i * 2654435761) >>> 0) % 1000) / 1000 * stride * 0.9);
    return out;
  }, [data]);

  const lon = (meta.bbox[0] + meta.bbox[2]) / 2;
  const lat = (meta.bbox[1] + meta.bbox[3]) / 2;
  const files = (meta.images?.files ?? []).map((f) => assetUrl(L.res.base, f));
  const aspect = meta.images ? meta.images.nx / meta.images.ny : meta.grid.nx / meta.grid.ny;
  const story = meta.story ?? {};
  const textRef = useReveal<HTMLDivElement>();

  return (
    <>
      <header className="page__head placehead">
        <a className="linkbtn" href="#/places">
          ← All places
        </a>
        <h1 className="sec__title">{meta.name}</h1>
        <div className="placehead__meta">
          {meta.country ? `${meta.country} · ` : ""}
          {formatLonLat(lon, lat)} · {T} NISAR passes, {fmtDate(meta.dates[0])} to {fmtDate(meta.dates[T - 1])}
        </div>
      </header>
      <div className="page__body">
        <div className="placemain">
          <div className="placemain__radar">
            <Timelapse files={files} dates={meta.dates} clock={clock} aspect={aspect} />
            <Scrubber dates={meta.dates} clock={clock} />
          </div>
          <div className="placemain__chart">
            <PlaceChart data={data} sample={sample} moveIds={moveIds} paths={paths} clock={clock} hhOnly={L.hhOnly} selected={selected} onPick={setSelected} />
            <Legend L={L} sampleN={sample.length} />
            {selected != null && <HectareCard L={L} k={selected} clock={clock} onClose={() => setSelected(null)} />}
          </div>
        </div>
        <div className="placetext reveal" ref={textRef}>
          <div>
            <div className="eyebrow">The story here</div>
            {story.title && <h2 className="placetext__title">{story.title}</h2>}
            {story.lede && <p className="sec__lede">{story.lede}</p>}
            {(story.body ?? []).map((p, i) => (
              <p key={i} className="placetext__p">
                {p}
              </p>
            ))}
          </div>
          <div>
            <div className="eyebrow">What changed here</div>
            <WhatChanged L={L} />
          </div>
        </div>
      </div>
    </>
  );
}

function Timelapse({ files, dates, clock, aspect }: { files: string[]; dates: string[]; clock: Clock; aspect: number }) {
  const a = useRef<HTMLImageElement>(null);
  const b = useRef<HTMLImageElement>(null);
  const { beat } = useClockBeat(clock);
  useEffect(() => {
    // warm the cache, nearest frames first
    const imgs: HTMLImageElement[] = [];
    files.forEach((f, i) => {
      const im = new Image();
      im.decoding = "async";
      window.setTimeout(() => (im.src = f), i * 120);
      imgs.push(im);
    });
    return () => imgs.forEach((im) => (im.src = ""));
  }, [files]);
  useEffect(
    () =>
      clock.subscribe((fr) => {
        if (!a.current || !b.current) return;
        const u0 = files[fr.i0];
        const u1 = files[fr.i1];
        if (u0 && a.current.dataset.u !== u0) {
          a.current.src = u0;
          a.current.dataset.u = u0;
        }
        if (u1 && b.current.dataset.u !== u1) {
          b.current.src = u1;
          b.current.dataset.u = u1;
        }
        b.current.style.opacity = fr.i1 === fr.i0 ? "0" : String(fr.e);
      }),
    [clock, files],
  );
  return (
    <div className="timelapse" style={{ aspectRatio: String(aspect) }}>
      <img ref={a} alt={`NISAR radar image, ${fmtDate(dates[beat])}`} decoding="async" />
      <img ref={b} alt="" decoding="async" style={{ opacity: 0 }} />
      <div className="timelapse__date">{fmtDate(dates[beat])}</div>
    </div>
  );
}

function Scrubber({ dates, clock }: { dates: string[]; clock: Clock }) {
  const { beat, playing } = useClockBeat(clock);
  const track = useRef<HTMLDivElement>(null);
  const head = useRef<HTMLDivElement>(null);
  const T = dates.length;
  const t0 = parseDate(dates[0]);
  const t1 = parseDate(dates[T - 1]);
  const pos = useMemo(() => dates.map((d) => (parseDate(d) - t0) / Math.max(1, t1 - t0)), [dates, t0, t1]);
  useEffect(
    () =>
      clock.subscribe((fr) => {
        if (!head.current) return;
        const f = pos[fr.i0] + (pos[fr.i1] - pos[fr.i0]) * fr.e;
        head.current.style.left = `${f * 100}%`;
      }),
    [clock, pos],
  );
  const seek = (clientX: number) => {
    if (!track.current) return;
    const r = track.current.getBoundingClientRect();
    const f = Math.min(1, Math.max(0, (clientX - r.left) / r.width));
    let best = 0;
    for (let i = 0; i < T; i++) if (Math.abs(pos[i] - f) < Math.abs(pos[best] - f)) best = i;
    clock.pause();
    clock.seek(best);
  };
  const drag = useRef(false);
  return (
    <div className="scrub">
      <button className="btn-play btn-play--sm" onClick={() => clock.toggle()} aria-label={playing ? "Pause" : "Play"}>
        {playing ? (
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden>
            <rect x="6" y="5" width="4" height="14" rx="1" fill="currentColor" />
            <rect x="14" y="5" width="4" height="14" rx="1" fill="currentColor" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden>
            <path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5z" fill="currentColor" />
          </svg>
        )}
      </button>
      <div className="scrub__date">
        <strong>{fmtDate(dates[beat])}</strong>
        <span>
          pass {beat + 1} of {T}
        </span>
      </div>
      <div
        className="scrub__track"
        ref={track}
        onPointerDown={(e) => {
          drag.current = true;
          (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
          seek(e.clientX);
        }}
        onPointerMove={(e) => drag.current && seek(e.clientX)}
        onPointerUp={() => (drag.current = false)}
        onPointerCancel={() => (drag.current = false)}
      >
        <div className="scrub__rail" />
        {pos.map((p, i) => (
          <i key={i} className={`scrub__tick ${i <= beat ? "is-past" : ""}`} style={{ left: `${p * 100}%` }} />
        ))}
        <div className="scrub__head" ref={head} />
      </div>
    </div>
  );
}

function Legend({ L, sampleN }: { L: Loaded; sampleN: number }) {
  const { data, res } = L;
  const ids = res.meta.moves?.ids;
  if (!data.moveCounts || !ids) return <p className="chart-caption">{fmtInt(sampleN)} of {fmtInt(data.K)} hectares shown.</p>;
  const total = data.moveCounts.reduce((a, b) => a + b, 0) || 1;
  return (
    <div className="plegend">
      {ids.map((m, i) =>
        data.moveCounts![i] ? (
          <span key={m}>
            <i style={{ background: CHANGE_COLOR[m] }} />
            {CHANGE_LABEL[m] ?? m} <em>{pct(data.moveCounts![i] / total)}</em>
          </span>
        ) : null,
      )}
      <span className="plegend__note">
        {fmtInt(sampleN)} of {fmtInt(data.K)} hectares shown. Click a dot to see its history.
      </span>
    </div>
  );
}

function pct(f: number) {
  const v = f * 100;
  return v >= 10 ? `${Math.round(v)}%` : v >= 1 ? `${v.toFixed(1)}%` : `${v.toFixed(2)}%`;
}

function WhatChanged({ L }: { L: Loaded }) {
  const { data, res } = L;
  const meta = res.meta;
  const ids = meta.moves?.ids;
  const T = meta.dates.length;
  const lines: string[] = [`NISAR passed over ${meta.name} ${T} times between ${fmtDate(meta.dates[0])} and ${fmtDate(meta.dates[T - 1])}. We followed ${fmtInt(data.K)} hectares, one dot each.`];
  if (data.moveCounts && ids) {
    const total = data.moveCounts.reduce((a, b) => a + b, 0) || 1;
    const ranked = ids
      .map((m, i) => ({ m, n: data.moveCounts![i] }))
      .filter((x) => x.m !== "still" && x.n / total >= 0.004)
      .sort((a, b) => b.n - a.n);
    ranked.slice(0, 2).forEach((x, i) => {
      const lab = (CHANGE_LABEL[x.m] ?? x.m).toLowerCase();
      lines.push(
        i === 0
          ? `${pct(x.n / total)} of them (${fmtInt(x.n)} hectares) show ${lab}: ${CHANGE_NOTE[x.m] ?? "a lasting change in the echoes"}.`
          : `Another ${pct(x.n / total)} show ${lab}${CHANGE_NOTE[x.m] ? `, where ${CHANGE_NOTE[x.m]}` : ""}.`,
      );
    });
    const still = ids.indexOf("still");
    if (still >= 0 && data.moveCounts[still]) lines.push(`${pct(data.moveCounts[still] / total)} show no change beyond the radar's speckle.`);
  }
  return (
    <div className="whatchanged">
      {lines.map((l, i) => (
        <p key={i}>{l}</p>
      ))}
    </div>
  );
}

function HectareCard({ L, k, clock, onClose }: { L: Loaded; k: number; clock: Clock; onClose: () => void }) {
  const { data, res, hhOnly } = L;
  const meta = res.meta;
  const T = data.T;
  const K = data.K;
  const ids = meta.moves?.ids;
  const move = data.move && ids ? ids[data.move[k]] : null;
  const conf = data.conf ? data.conf[k] : null;
  const hh: (number | null)[] = [];
  const hv: (number | null)[] = [];
  for (let t = 0; t < T; t++) {
    const ok = data.valid[t * K + k];
    hh.push(ok ? data.xy[(t * K + k) * 2 + (hhOnly ? 1 : 0)] : null);
    hv.push(ok && !hhOnly ? data.xy[(t * K + k) * 2 + 1] : null);
  }
  const W = 340;
  const H = 130;
  const m = { l: 30, r: 28, t: 10, b: 20 };
  const t0 = parseDate(meta.dates[0]);
  const t1 = parseDate(meta.dates[T - 1]);
  const xs = meta.dates.map((d) => m.l + ((parseDate(d) - t0) / Math.max(1, t1 - t0)) * (W - m.l - m.r));
  const vals = [...hh, ...hv].filter((v): v is number => v != null);
  const lo = Math.floor((Math.min(...vals) - 1) / 2) * 2;
  const hi = Math.ceil((Math.max(...vals) + 1) / 2) * 2;
  const Y = (v: number) => m.t + ((hi - v) / Math.max(1, hi - lo)) * (H - m.t - m.b);
  const line = (s: (number | null)[]) => {
    let d = "";
    let pen = false;
    s.forEach((v, i) => {
      if (v == null) {
        pen = false;
        return;
      }
      d += `${pen ? "L" : "M"}${xs[i].toFixed(1)},${Y(v).toFixed(1)}`;
      pen = true;
    });
    return d;
  };
  const cursor = useRef<SVGLineElement>(null);
  useEffect(
    () =>
      clock.subscribe((fr) => {
        if (!cursor.current) return;
        const x = xs[fr.i0] + (xs[fr.i1] - xs[fr.i0]) * fr.e;
        cursor.current.setAttribute("x1", String(x));
        cursor.current.setAttribute("x2", String(x));
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [clock],
  );
  const n = data.idx[k];
  const lastHH = [...hh].reverse().find((v) => v != null);
  const lastHV = [...hv].reverse().find((v) => v != null);
  return (
    <div className="hcard" role="dialog" aria-label="One hectare">
      <div className="hcard__head">
        <div>
          <div className="eyebrow">One hectare</div>
          <div className="hcard__where">{formatLonLat(data.lonlat[k * 2], data.lonlat[k * 2 + 1])}</div>
        </div>
        <button className="btn-icon" onClick={onClose} aria-label="Close">
          <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden>
            <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </button>
      </div>
      {move && (
        <div className="hcard__move">
          <i style={{ background: CHANGE_COLOR[move] }} />
          {CHANGE_LABEL[move] ?? move}
          {conf != null && <span>{conf}% confidence</span>}
        </div>
      )}
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" aria-label="HH and HV of this hectare over time">
        {[lo, (lo + hi) / 2, hi].map((v) => (
          <g key={v}>
            <line x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} className="chart__grid" />
            <text x={m.l - 6} y={Y(v) + 3} textAnchor="end" className="chart__tick">
              {fmtDb(v, 0)}
            </text>
          </g>
        ))}
        <line ref={cursor} y1={m.t - 2} y2={H - m.b} className="chart__cursor" />
        {!hhOnly && <path d={line(hv)} fill="none" stroke="#7fd1c7" strokeWidth={2} strokeLinejoin="round" />}
        <path d={line(hh)} fill="none" stroke="#ffb38a" strokeWidth={2} strokeLinejoin="round" />
        {lastHH != null && (
          <text x={W - m.r + 5} y={Y(lastHH) + 3.5} className="chart__label" style={{ fill: "#ffb38a" }}>
            HH
          </text>
        )}
        {lastHV != null && !hhOnly && (
          <text x={W - m.r + 5} y={Y(lastHV) + 3.5} className="chart__label" style={{ fill: "#7fd1c7" }}>
            HV
          </text>
        )}
        <text x={m.l} y={H - 4} className="chart__tick">
          {fmtDate(meta.dates[0], { year: false })}
        </text>
        <text x={W - m.r} y={H - 4} className="chart__tick" textAnchor="end">
          {fmtDate(meta.dates[T - 1])}
        </text>
      </svg>
      <div className="hcard__foot">Hectare #{fmtInt(n)} · dB, pass by pass</div>
    </div>
  );
}

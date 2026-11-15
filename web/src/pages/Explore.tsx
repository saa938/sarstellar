import { useEffect, useRef, useState } from "react";
import type { Map as MLMap, Marker } from "maplibre-gl";
import { Nav } from "../components/Nav";
import { Footer } from "../components/Footer";
import { FixtureTag } from "../components/FixtureTag";
import { API_URL, loadIndex, type IndexResult } from "../lib/data";
import { maplibregl, DARK_LABELS, ESRI_ATTR, ESRI_IMAGERY, GIBS_ATTR, GIBS_BLACK_MARBLE } from "../lib/maplibre";
import type { GeoJSONSource } from "maplibre-gl";
import { MOVE_COLORS, MOVE_NAMES } from "../lib/moves";
import { StageCard } from "./Landing";

type Live =
  | { phase: "idle" }
  | { phase: "drawing" }
  | { phase: "boxed"; bbox: [number, number, number, number]; wkm: number; hkm: number; ok: boolean }
  | { phase: "running"; id: string; status: string; progress: number; message: string; bbox: [number, number, number, number] }
  | { phase: "error"; message: string };

function sizeKm(b: [number, number, number, number]) {
  const lat = ((b[1] + b[3]) / 2) * (Math.PI / 180);
  return { w: (b[2] - b[0]) * 111.32 * Math.cos(lat), h: (b[3] - b[1]) * 110.57 };
}

export default function Explore() {
  const [idx, setIdx] = useState<IndexResult | null>(null);
  const el = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const [live, setLive] = useState<Live>({ phase: "idle" });
  const [box, setBox] = useState<null | { x0: number; y0: number; x1: number; y1: number }>(null);
  const drag = useRef<null | { x0: number; y0: number; x1: number; y1: number }>(null);

  useEffect(() => {
    loadIndex().then(setIdx);
  }, []);

  useEffect(() => {
    if (!el.current || !idx) return;
    const map = new maplibregl.Map({
      container: el.current,
      style: {
        version: 8,
        projection: { type: "globe" },
        sky: { "sky-color": "#06070b", "horizon-color": "#203a66", "fog-color": "#06070b", "atmosphere-blend": 0.85 },
        sources: {
          night: { type: "raster", tiles: [GIBS_BLACK_MARBLE], tileSize: 256, maxzoom: 8, attribution: GIBS_ATTR },
          labels: { type: "raster", tiles: DARK_LABELS, tileSize: 256, maxzoom: 16 },
          sat: { type: "raster", tiles: [ESRI_IMAGERY], tileSize: 256, maxzoom: 18, attribution: ESRI_ATTR },
          livebox: { type: "geojson", data: { type: "FeatureCollection", features: [] } },
        },
        layers: [
          { id: "bg", type: "background", paint: { "background-color": "#06070b" } },
          { id: "night", type: "raster", source: "night", paint: { "raster-contrast": 0.1 } },
          { id: "sat", type: "raster", source: "sat", layout: { visibility: "none" }, paint: { "raster-saturation": -0.2, "raster-brightness-max": 0.8 } },
          { id: "labels", type: "raster", source: "labels", minzoom: 4, paint: { "raster-opacity": 0.6 } },
          { id: "livebox-fill", type: "fill", source: "livebox", paint: { "fill-color": "#f2d08a", "fill-opacity": 0.1 } },
          { id: "livebox", type: "line", source: "livebox", paint: { "line-color": "#f2d08a", "line-width": 1.6 } },
        ],
      },
      center: [20, 20],
      zoom: 1.3,
      attributionControl: { compact: true },
      dragRotate: false,
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    const markers: Marker[] = [];
    for (const s of idx.index.stages) {
      const m = document.createElement("a");
      m.href = `#/stage/${s.id}`;
      m.className = "pin";
      m.style.setProperty("--mc", MOVE_COLORS[s.move] ?? "#f2d08a");
      m.innerHTML = `<i></i><span><b>${escapeHtml(s.name)}</b><em>${escapeHtml(MOVE_NAMES[s.move] ?? s.move)} · ${s.n_passes} passes</em></span>`;
      markers.push(new maplibregl.Marker({ element: m, anchor: "left", offset: [-7, 0] }).setLngLat(s.center).addTo(map));
    }
    if (idx.index.stages.length) {
      // center on the stages, globe filling the frame
      const st = idx.index.stages;
      const lng = st.reduce((a, s) => a + s.center[0], 0) / st.length;
      const lat = st.reduce((a, s) => a + s.center[1], 0) / st.length;
      const r = el.current.getBoundingClientRect();
      map.jumpTo({ center: [lng, Math.max(-30, Math.min(40, lat))], zoom: Math.log2((Math.min(r.width, r.height) * 0.46) / 81.5) });
    }
    return () => {
      markers.forEach((m) => m.remove());
      map.remove();
      mapRef.current = null;
    };
  }, [idx]);

  // ---- live mode
  const startDrawing = () => {
    const map = mapRef.current;
    if (!map) return;
    map.setProjection({ type: "mercator" });
    map.setLayoutProperty("sat", "visibility", "visible");
    if (map.getZoom() < 8.5) map.flyTo({ zoom: 9.6, duration: 900 });
    map.dragPan.disable();
    setLive({ phase: "drawing" });
  };
  const stopDrawing = () => {
    mapRef.current?.dragPan.enable();
  };
  const local = (e: React.PointerEvent) => {
    const r = el.current!.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  };
  const onDown = (e: React.PointerEvent) => {
    const [x, y] = local(e);
    drag.current = { x0: x, y0: y, x1: x, y1: y };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    setBox({ ...drag.current });
  };
  const onMove = (e: React.PointerEvent) => {
    if (!drag.current) return;
    const [x, y] = local(e);
    drag.current.x1 = x;
    drag.current.y1 = y;
    setBox({ ...drag.current });
  };
  const onUp = () => {
    const d = drag.current;
    drag.current = null;
    const map = mapRef.current;
    if (!d || !map) return;
    stopDrawing();
    const a = map.unproject([Math.min(d.x0, d.x1), Math.max(d.y0, d.y1)]);
    const c = map.unproject([Math.max(d.x0, d.x1), Math.min(d.y0, d.y1)]);
    const bbox: [number, number, number, number] = [round(a.lng), round(a.lat), round(c.lng), round(c.lat)];
    const { w, h } = sizeKm(bbox);
    (map.getSource("livebox") as GeoJSONSource | undefined)?.setData({
      type: "Feature",
      properties: {},
      geometry: { type: "Polygon", coordinates: [[[bbox[0], bbox[1]], [bbox[2], bbox[1]], [bbox[2], bbox[3]], [bbox[0], bbox[3]], [bbox[0], bbox[1]]]] },
    });
    setLive({ phase: "boxed", bbox, wkm: w, hkm: h, ok: w >= 1 && h >= 1 && w <= 25 && h <= 25 });
  };

  const submit = async (bbox: [number, number, number, number]) => {
    if (!API_URL) return;
    try {
      const r = await fetch(`${API_URL}/dance`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ bbox }) });
      if (!r.ok) throw new Error(`The live service answered ${r.status}.`);
      const { id } = (await r.json()) as { id: string };
      setLive({ phase: "running", id, status: "queued", progress: 0, message: "Waiting for a worker", bbox });
    } catch (e) {
      setLive({ phase: "error", message: String((e as Error).message || e) });
    }
  };

  useEffect(() => {
    if (live.phase !== "running" || !API_URL) return;
    let dead = false;
    const id = live.id;
    const poll = async () => {
      try {
        const r = await fetch(`${API_URL}/dance/${encodeURIComponent(id)}`);
        if (!r.ok) throw new Error(`status ${r.status}`);
        const j = (await r.json()) as { status: string; progress?: number; message?: string };
        if (dead) return;
        if (j.status === "done") {
          window.location.hash = `#/stage/live:${encodeURIComponent(id)}`;
          return;
        }
        if (j.status === "error") {
          setLive({ phase: "error", message: j.message || "The live run failed." });
          return;
        }
        setLive((s) => (s.phase === "running" ? { ...s, status: j.status, progress: j.progress ?? s.progress, message: j.message ?? s.message } : s));
        setTimeout(poll, 1500);
      } catch (e) {
        if (!dead) setLive({ phase: "error", message: `Lost contact with the live service (${String((e as Error).message || e)}).` });
      }
    };
    const t = setTimeout(poll, 800);
    return () => {
      dead = true;
      clearTimeout(t);
    };
  }, [live.phase, live.phase === "running" ? live.id : null]); // eslint-disable-line react-hooks/exhaustive-deps

  const stages = idx?.index.stages ?? [];
  return (
    <div className="page">
      <Nav active="explore" />
      <header className="page__head">
        <div className="eyebrow">Explore</div>
        <h1 className="act__title">Every stage</h1>
        <p className="act__lede" style={{ maxWidth: 760 }}>
          Each light is a place where NISAR's passes have been turned into a dance. Click one to open it.
          {API_URL ? " Or draw your own box anywhere NISAR has flown and watch it assemble live." : ""}
        </p>
        {idx?.fixture && (
          <div style={{ marginTop: 16 }}>
            <FixtureTag />
          </div>
        )}
      </header>
      <div className="page__body">
        <div className="exploremap">
          <div ref={el} className="exploremap__map" />
          {live.phase === "drawing" && (
            <div className="exploremap__draw" onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}>
              {box && (
                <div className="stagemap__box" style={{ left: Math.min(box.x0, box.x1), top: Math.min(box.y0, box.y1), width: Math.abs(box.x1 - box.x0), height: Math.abs(box.y1 - box.y0) }}>
                  <BoxSize map={mapRef.current} box={box} />
                </div>
              )}
            </div>
          )}
          {API_URL && (
            <div className="livepanel">
              <div className="eyebrow">Live</div>
              {live.phase === "idle" && (
                <>
                  <p>Pan to any place NISAR has flown, then draw a box 1 to 25 km on a side. Every pass is read in parallel and the dance assembles here.</p>
                  <button className="btn btn--primary" onClick={startDrawing}>
                    Draw a box
                  </button>
                </>
              )}
              {live.phase === "drawing" && <p>Drag on the map to draw your box.</p>}
              {live.phase === "boxed" && (
                <>
                  <p>
                    {live.wkm.toFixed(1)} km × {live.hkm.toFixed(1)} km{" "}
                    {!live.ok && <span className="livepanel__warn">Each side must be between 1 and 25 km.</span>}
                  </p>
                  <div className="hero__ctas" style={{ marginTop: 10 }}>
                    <button className="btn btn--primary" disabled={!live.ok} onClick={() => submit(live.bbox)}>
                      Start the dance
                    </button>
                    <button className="btn" onClick={startDrawing}>
                      Redraw
                    </button>
                  </div>
                </>
              )}
              {live.phase === "running" && (
                <>
                  <p>{live.message || "Reading passes"}</p>
                  <div className="beats" aria-label={`${Math.round(live.progress * 100)}% done`}>
                    {Array.from({ length: 16 }, (_, i) => (
                      <i key={i} className={i < Math.round(live.progress * 16) ? "is-on" : ""} />
                    ))}
                  </div>
                  <p className="dim">Beats arriving: {Math.round(live.progress * 100)}% · {live.status}</p>
                </>
              )}
              {live.phase === "error" && (
                <>
                  <p className="livepanel__warn">{live.message}</p>
                  <button className="btn" onClick={() => setLive({ phase: "idle" })}>
                    Try again
                  </button>
                </>
              )}
            </div>
          )}
        </div>
        <div className="tour" style={{ marginTop: 36 }}>
          {stages.map((s) => (
            <StageCard key={s.id} s={s} root={idx?.base ?? ""} />
          ))}
        </div>
      </div>
      <Footer />
    </div>
  );
}

function round(v: number) {
  return Math.round(v * 1e5) / 1e5;
}

function escapeHtml(s: string) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}

function BoxSize({ map, box }: { map: MLMap | null; box: { x0: number; y0: number; x1: number; y1: number } }) {
  if (!map) return null;
  const a = map.unproject([Math.min(box.x0, box.x1), Math.max(box.y0, box.y1)]);
  const c = map.unproject([Math.max(box.x0, box.x1), Math.min(box.y0, box.y1)]);
  const { w, h } = sizeKm([a.lng, a.lat, c.lng, c.lat]);
  const ok = w >= 1 && h >= 1 && w <= 25 && h <= 25;
  return (
    <span className={`boxsize ${ok ? "" : "is-bad"}`}>
      {w.toFixed(1)} × {h.toFixed(1)} km
    </span>
  );
}

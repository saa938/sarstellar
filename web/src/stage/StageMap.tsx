import { useEffect, useRef, useState } from "react";
import type { Map as MLMap, ImageSource, GeoJSONSource, StyleSpecification } from "maplibre-gl";
import type { Feature, FeatureCollection } from "geojson";
import { maplibregl, DARK_ATTR, DARK_BASE, DARK_LABELS, ESRI_ATTR, ESRI_IMAGERY } from "../lib/maplibre";
import type { StageMeta } from "../lib/types";
import type { DecodeResult } from "./decoded";
import type { Clock, Frame } from "./clock";
import type { Signal } from "../lib/signal";
import { blockPolygon, quadInverse } from "../lib/geo";
import { assetUrl } from "../lib/data";

const SLOTS = 4;
const EMPTY_FC = { type: "FeatureCollection" as const, features: [] as Feature[] };

class RadarImages {
  private cache = new Map<number, Promise<ImageBitmap | null>>();
  private order: number[] = [];
  private urls: string[];
  constructor(urls: string[]) {
    this.urls = urls;
  }
  get(t: number): Promise<ImageBitmap | null> {
    let p = this.cache.get(t);
    if (p) {
      this.order = this.order.filter((x) => x !== t);
      this.order.push(t);
      return p;
    }
    const url = this.urls[t];
    if (!url) return Promise.resolve(null);
    p = fetch(url)
      .then((r) => (r.ok ? r.blob() : Promise.reject(new Error(String(r.status)))))
      .then((b) => createImageBitmap(b))
      .catch(() => null);
    this.cache.set(t, p);
    this.order.push(t);
    while (this.order.length > 12) {
      const old = this.order.shift()!;
      this.cache.delete(old);
    }
    return p;
  }
}

export type Basemap = "dark" | "satellite";

interface Props {
  meta: StageMeta;
  base: string;
  data: DecodeResult;
  clock: Clock;
  hover: Signal<number>;
  solo: number | null;
  selection: Uint8Array | null;
  selVersion: number;
  basemap: Basemap;
  showMoves: boolean;
  moveColors: [number, number, number][] | null;
  boxTool: boolean;
  onPick: (k: number | null) => void;
  onSelect: (mask: Uint8Array | null, count: number, final: boolean) => void;
  onBoxDone?: () => void;
  radarOn: boolean;
}

export function StageMap(props: Props) {
  const { meta, base, data, clock, hover, solo, selection, selVersion, basemap, showMoves, moveColors, boxTool, onPick, onSelect, onBoxDone, radarOn } = props;
  const el = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const [ready, setReady] = useState(false);
  const slotT = useRef<number[]>(new Array(SLOTS).fill(-1));
  const slotReady = useRef<boolean[]>(new Array(SLOTS).fill(false));
  const opac = useRef<number[]>(new Array(SLOTS).fill(-1));
  const imgs = useRef<RadarImages | null>(null);
  const radarDim = useRef(1);
  const radarOnRef = useRef(radarOn);
  radarOnRef.current = radarOn;
  const lastFrame = useRef<Frame>(clock.frame());
  const cb = useRef({ onPick, onSelect, onBoxDone });
  cb.current = { onPick, onSelect, onBoxDone };
  const [box, setBox] = useState<null | { x0: number; y0: number; x1: number; y1: number }>(null);

  const files = meta.images?.files ?? [];
  const hasImages = files.length > 0;

  // ---- create map
  useEffect(() => {
    if (!el.current) return;
    imgs.current = new RadarImages(files.map((f) => assetUrl(base, f)));
    const corners = meta.corners as [[number, number], [number, number], [number, number], [number, number]];
    const sources: StyleSpecification["sources"] = {
      carto: { type: "raster", tiles: DARK_BASE, tileSize: 256, attribution: DARK_ATTR, maxzoom: 16 },
      labels: { type: "raster", tiles: DARK_LABELS, tileSize: 256, maxzoom: 16 },
      esri: { type: "raster", tiles: [ESRI_IMAGERY], tileSize: 256, attribution: ESRI_ATTR, maxzoom: 19 },
      sel: { type: "image", coordinates: corners },
      mv: { type: "image", coordinates: corners },
      hovercell: { type: "geojson", data: EMPTY_FC },
      solocell: { type: "geojson", data: EMPTY_FC },
      outline: {
        type: "geojson",
        data: { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [[...corners, corners[0]]] } },
      },
    };
    for (let i = 0; i < SLOTS; i++) sources[`radar${i}`] = { type: "image", coordinates: corners };
    const layers: StyleSpecification["layers"] = [
      { id: "bg", type: "background", paint: { "background-color": "#06070b" } },
      { id: "carto", type: "raster", source: "carto", paint: { "raster-opacity": 1, "raster-brightness-max": 0.42, "raster-contrast": 0.1, "raster-saturation": -0.3, "raster-fade-duration": 150 } },
      { id: "esri", type: "raster", source: "esri", layout: { visibility: "none" }, paint: { "raster-opacity": 0.85, "raster-saturation": -0.25, "raster-fade-duration": 150 } },
    ];
    for (let i = 0; i < SLOTS; i++)
      layers.push({
        id: `radar${i}`,
        type: "raster",
        source: `radar${i}`,
        paint: { "raster-opacity": 0, "raster-opacity-transition": { duration: 0, delay: 0 }, "raster-fade-duration": 0, "raster-resampling": "linear" },
      });
    layers.push(
      { id: "mv", type: "raster", source: "mv", layout: { visibility: "none" }, paint: { "raster-opacity": 0.82, "raster-fade-duration": 0, "raster-resampling": "nearest" } },
      { id: "sel", type: "raster", source: "sel", layout: { visibility: "none" }, paint: { "raster-opacity": 1, "raster-fade-duration": 0, "raster-resampling": "nearest" } },
      { id: "labels", type: "raster", source: "labels", paint: { "raster-opacity": 0.7 } },
      { id: "outline", type: "line", source: "outline", paint: { "line-color": "#f4ecd8", "line-opacity": 0.35, "line-width": 1, "line-dasharray": [2, 2] } },
      { id: "hovercell", type: "line", source: "hovercell", paint: { "line-color": "#ffffff", "line-width": 1.6, "line-opacity": 0.95 } },
      { id: "solocell-glow", type: "line", source: "solocell", paint: { "line-color": "#f2d08a", "line-width": 7, "line-opacity": 0.25, "line-blur": 3 } },
      { id: "solocell", type: "line", source: "solocell", paint: { "line-color": "#f2d08a", "line-width": 2 } },
    );
    const [w, s, e, n] = meta.bbox;
    const map = new maplibregl.Map({
      container: el.current,
      style: { version: 8, sources, layers },
      bounds: [
        [w, s],
        [e, n],
      ],
      fitBoundsOptions: { padding: 24 },
      attributionControl: { compact: true },
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      renderWorldCopies: false,
      maxPitch: 0,
      fadeDuration: 0,
    });
    map.touchZoomRotate.disableRotation();
    map.keyboard.disable();
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    mapRef.current = map;
    if (import.meta.env.DEV) (window as unknown as { __map: MLMap }).__map = map;
    // empty image sources keep the style from ever reporting "loaded", so start feeding images as
    // soon as the style itself is parsed
    const onStyle = () => setReady(true);
    if (map.isStyleLoaded()) onStyle();
    map.once("style.load", onStyle);

    const pickK = (lng: number, lat: number) => {
      const [u, v] = quadInverse(corners, lng, lat);
      if (u < 0 || u >= 1 || v < 0 || v >= 1) return -1;
      const col = Math.floor(u * meta.grid.nx);
      const row = Math.floor(v * meta.grid.ny);
      return data.nToK[row * meta.grid.nx + col] ?? -1;
    };
    let raf = 0;
    map.on("mousemove", (ev) => {
      if (raf) return;
      const { lng, lat } = ev.lngLat;
      raf = requestAnimationFrame(() => {
        raf = 0;
        hover.set(pickK(lng, lat));
      });
    });
    map.on("mouseout", () => hover.set(-1));
    map.on("click", (ev) => {
      const k = pickK(ev.lngLat.lng, ev.lngLat.lat);
      cb.current.onPick(k >= 0 ? k : null);
    });
    return () => {
      cancelAnimationFrame(raf);
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta, base, data]);

  // ---- radar crossfade on every frame
  useEffect(() => {
    if (!ready || !hasImages) return;
    const map = mapRef.current!;
    const ensure = (t: number) => {
      const s = t % SLOTS;
      if (slotT.current[s] === t) return;
      slotT.current[s] = t;
      slotReady.current[s] = false;
      imgs.current!.get(t).then((bmp) => {
        if (!bmp || slotT.current[s] !== t || !mapRef.current) return;
        const src = map.getSource(`radar${s}`) as ImageSource | undefined;
        src?.updateImage({ image: bmp });
        slotReady.current[s] = true;
        apply(lastFrame.current);
      });
    };
    const setOp = (s: number, v: number) => {
      const val = Math.round(v * 1000) / 1000;
      if (Math.abs(opac.current[s] - val) < 0.003) return;
      opac.current[s] = val;
      map.setPaintProperty(`radar${s}`, "raster-opacity", val);
    };
    const apply = (fr: Frame) => {
      const T = files.length;
      const i0 = Math.min(fr.i0, T - 1);
      const i1 = Math.min(fr.i1, T - 1);
      ensure(i0);
      ensure(i1);
      if (i1 + 1 < T) imgs.current!.get(i1 + 1);
      if (i1 + 2 < T) imgs.current!.get(i1 + 2);
      const s0 = i0 % SLOTS;
      const s1 = i1 % SLOTS;
      const r0 = slotReady.current[s0];
      const r1 = slotReady.current[s1];
      const dim = radarOnRef.current ? radarDim.current : 0;
      const want = new Array(SLOTS).fill(0);
      if (r0 && r1 && s0 !== s1) {
        if (s1 > s0) {
          want[s0] = 1;
          want[s1] = fr.e;
        } else {
          want[s1] = 1;
          want[s0] = 1 - fr.e;
        }
      } else if (r0) want[s0] = 1;
      else if (r1) want[s1] = 1;
      else return; // keep whatever is showing until the new pass decodes
      for (let s = 0; s < SLOTS; s++) setOp(s, want[s] * dim);
    };
    const unsub = clock.subscribe((fr) => {
      lastFrame.current = fr;
      apply(fr);
    });
    return unsub;
  }, [ready, clock, hasImages, files.length]);

  // ---- basemap
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.setLayoutProperty("carto", "visibility", basemap === "dark" ? "visible" : "none");
    map.setLayoutProperty("esri", "visibility", basemap === "satellite" ? "visible" : "none");
  }, [ready, basemap]);

  // ---- radar on/off and dimming under a selection
  useEffect(() => {
    radarDim.current = 1;
    opac.current.fill(-1);
    clock.invalidate();
  }, [selection, selVersion, radarOn, clock]);

  // ---- selection overlay
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    if (!selection) {
      map.setLayoutProperty("sel", "visibility", "none");
      return;
    }
    const { nx, ny } = meta.grid;
    const img = new ImageData(nx, ny);
    const px = img.data;
    // spotlight: veil every hectare outside the selection, tint the selection faintly gold
    for (let k = 0; k < data.K; k++) {
      const o = data.idx[k] * 4;
      if (selection[k]) {
        px[o] = 255;
        px[o + 1] = 214;
        px[o + 2] = 140;
        px[o + 3] = 52;
      } else {
        px[o] = 5;
        px[o + 1] = 6;
        px[o + 2] = 10;
        px[o + 3] = 200;
      }
    }
    (map.getSource("sel") as ImageSource).updateImage({ image: img });
    map.setLayoutProperty("sel", "visibility", "visible");
  }, [ready, selection, selVersion, data, meta]);

  // ---- move overlay
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    if (!showMoves || !data.move || !moveColors) {
      map.setLayoutProperty("mv", "visibility", "none");
      return;
    }
    const { nx, ny } = meta.grid;
    const img = new ImageData(nx, ny);
    const px = img.data;
    for (let k = 0; k < data.K; k++) {
      const m = data.move[k];
      if (m === 0 || m >= moveColors.length) continue; // still or none: let the radar show
      const c = moveColors[m];
      const o = data.idx[k] * 4;
      px[o] = c[0];
      px[o + 1] = c[1];
      px[o + 2] = c[2];
      px[o + 3] = 215;
    }
    (map.getSource("mv") as ImageSource).updateImage({ image: img });
    map.setLayoutProperty("mv", "visibility", "visible");
  }, [ready, showMoves, data, moveColors, meta]);

  // ---- hover and solo outlines
  useEffect(() => {
    if (!ready) return;
    const map = mapRef.current!;
    const corners = meta.corners as [[number, number], [number, number], [number, number], [number, number]];
    const poly = (k: number): FeatureCollection => {
      if (k < 0) return EMPTY_FC;
      const ring = blockPolygon(corners, meta.grid.nx, meta.grid.ny, data.idx[k]);
      return { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [ring] } }] };
    };
    const on = (k: number) => (map.getSource("hovercell") as GeoJSONSource | undefined)?.setData(poly(k));
    on(hover.get());
    return hover.subscribe(on);
  }, [ready, hover, data, meta]);

  useEffect(() => {
    if (!ready) return;
    const map = mapRef.current!;
    const corners = meta.corners as [[number, number], [number, number], [number, number], [number, number]];
    const src = map.getSource("solocell") as GeoJSONSource | undefined;
    if (solo == null || solo < 0) {
      src?.setData(EMPTY_FC);
      return;
    }
    const ring = blockPolygon(corners, meta.grid.nx, meta.grid.ny, data.idx[solo]);
    src?.setData({ type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [ring] } }] });
    // keep the soloed hectare in view
    const [lng, lat] = [data.lonlat[solo * 2], data.lonlat[solo * 2 + 1]];
    if (!map.getBounds().contains([lng, lat])) map.easeTo({ center: [lng, lat], duration: 600 });
  }, [ready, solo, data, meta]);

  // ---- box select on the map
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    if (boxTool) map.dragPan.disable();
    else map.dragPan.enable();
  }, [ready, boxTool]);

  const boxRef = useRef<null | { x0: number; y0: number; x1: number; y1: number; id: number }>(null);
  const selRaf = useRef(0);
  const runBox = (b: { x0: number; y0: number; x1: number; y1: number }, final: boolean) => {
    const map = mapRef.current;
    if (!map) return;
    const a = map.unproject([Math.min(b.x0, b.x1), Math.min(b.y0, b.y1)]);
    const c = map.unproject([Math.max(b.x0, b.x1), Math.max(b.y0, b.y1)]);
    const w = Math.min(a.lng, c.lng);
    const e = Math.max(a.lng, c.lng);
    const s = Math.min(a.lat, c.lat);
    const n = Math.max(a.lat, c.lat);
    const mask = new Uint8Array(data.K);
    let count = 0;
    for (let k = 0; k < data.K; k++) {
      const lng = data.lonlat[k * 2];
      const lat = data.lonlat[k * 2 + 1];
      if (lng >= w && lng <= e && lat >= s && lat <= n) {
        mask[k] = 1;
        count++;
      }
    }
    cb.current.onSelect(count ? mask : null, count, final);
  };
  const onBoxDown = (ev: React.PointerEvent) => {
    const r = el.current!.getBoundingClientRect();
    const x = ev.clientX - r.left;
    const y = ev.clientY - r.top;
    boxRef.current = { x0: x, y0: y, x1: x, y1: y, id: ev.pointerId };
    (ev.currentTarget as HTMLElement).setPointerCapture(ev.pointerId);
    setBox({ x0: x, y0: y, x1: x, y1: y });
  };
  const onBoxMove = (ev: React.PointerEvent) => {
    const b = boxRef.current;
    if (!b) return;
    const r = el.current!.getBoundingClientRect();
    b.x1 = ev.clientX - r.left;
    b.y1 = ev.clientY - r.top;
    setBox({ ...b });
    if (!selRaf.current)
      selRaf.current = requestAnimationFrame(() => {
        selRaf.current = 0;
        if (boxRef.current) runBox(boxRef.current, false);
      });
  };
  const onBoxUp = () => {
    const b = boxRef.current;
    boxRef.current = null;
    setBox(null);
    if (!b) return;
    if (Math.abs(b.x1 - b.x0) < 4 && Math.abs(b.y1 - b.y0) < 4) {
      cb.current.onSelect(null, 0, true);
    } else runBox(b, true);
    cb.current.onBoxDone?.();
  };

  return (
    <div className="stagemap">
      <div ref={el} className="stagemap__map" />
      {boxTool && (
        <div className="stagemap__boxlayer" onPointerDown={onBoxDown} onPointerMove={onBoxMove} onPointerUp={onBoxUp} onPointerCancel={onBoxUp}>
          {box && (
            <div
              className="stagemap__box"
              style={{ left: Math.min(box.x0, box.x1), top: Math.min(box.y0, box.y1), width: Math.abs(box.x1 - box.x0), height: Math.abs(box.y1 - box.y0) }}
            />
          )}
        </div>
      )}
    </div>
  );
}

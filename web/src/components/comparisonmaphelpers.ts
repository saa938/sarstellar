// MapLibre helpers shared by the Before | After swipe and the L-band vs C-band views (Task B5).
import { Map as MapLibreMap, NavigationControl, type GeoJSONSource, type MapOptions } from "maplibre-gl";
import Compare from "@maplibre/maplibre-gl-compare";
import "../pages/maplibreWorker.ts";
import { AGREEMENT_COLORS, type Bbox, type ChangeArea, type IsoDate, type Overlays } from "../types.ts";
import { createBasemapStyle } from "./mapModel.ts";

type Style = Exclude<MapOptions["style"], string | undefined>;

export interface RadarLayer {
  url: string;
  corners: Overlays["bounds"];
  /** "nearest" keeps 1-ha change blocks crisp; "linear" (default) smooths backscatter images. */
  resampling?: "nearest" | "linear";
  /** Change areas to outline on top, colored by agreement. */
  outline?: readonly ChangeArea[];
  /** The selected candidate patch remains visible regardless of its majority category. */
  selectedArea?: ChangeArea | null;
}

function selectedFeatures(area: ChangeArea | null | undefined) {
  return { type: "FeatureCollection" as const, features: area ? [{
    type: "Feature" as const, properties: { id: area.id }, geometry: area.geometry,
  }] : [] };
}

/** Update the highlight without recreating or moving a comparison map. Call again on map load. */
export function updateSelectedArea(map: MapLibreMap, area: ChangeArea | null | undefined): void {
  if (!map.isStyleLoaded()) return;
  (map.getSource("selected-area") as GeoJSONSource | undefined)?.setData(selectedFeatures(area));
}

/** Muted Esri imagery (as in the mockup), one radar image at its corners, and optional area outlines. */
export function radarStyle({ url, corners, resampling = "linear", outline = [], selectedArea }: RadarLayer) {
  const basemap = createBasemapStyle();
  const features = outline.map((a) => ({ type: "Feature" as const, properties: { agreement: a.agreement }, geometry: a.geometry }));
  return {
    version: 8,
    sources: {
      ...basemap.sources,
      radar: { type: "image", url: overlayUrl(url), coordinates: corners },
      areas: { type: "geojson", data: { type: "FeatureCollection", features } },
      "selected-area": { type: "geojson", data: selectedFeatures(selectedArea) },
    },
    layers: [
      ...basemap.layers,
      { id: "radar", type: "raster", source: "radar", paint: { "raster-resampling": resampling, "raster-fade-duration": 0 } },
      {
        id: "areas",
        type: "line",
        source: "areas",
        paint: {
          "line-color": ["match", ["get", "agreement"], "L", AGREEMENT_COLORS.L, "both", AGREEMENT_COLORS.both, AGREEMENT_COLORS.C],
          "line-width": 1.5,
        },
      },
      { id: "selected-area-halo", type: "line", source: "selected-area",
        paint: { "line-color": "#202223", "line-width": 6, "line-opacity": 0.95 } },
      { id: "selected-area-outline", type: "line", source: "selected-area",
        paint: { "line-color": "#ffffff", "line-width": 3, "line-opacity": 1 } },
    ],
  } satisfies Style;
}

/** API/story loaders already normalize URLs; this also accepts safe standalone relative URLs. */
export function overlayUrl(url: string): string {
  if (!url.trim()) throw new Error("The radar image is missing.");
  const resolved = new URL(url, globalThis.location?.href ?? "http://localhost/");
  if (!["http:", "https:", "blob:"].includes(resolved.protocol) && !/^data:image\/(png|jpeg|webp);/i.test(url)) {
    throw new Error("The radar image URL is unavailable.");
  }
  return resolved.href;
}

/** Parent panels change size without a window resize; keep all viewports fitted to their containers. */
export function observeMaps(container: HTMLElement, maps: MapLibreMap[], afterResize?: () => void): () => void {
  if (typeof ResizeObserver === "undefined") return () => {};
  const observer = new ResizeObserver(() => {
    maps.forEach((map) => map.resize());
    afterResize?.();
  });
  observer.observe(container);
  return () => observer.disconnect();
}

/** A map showing one radar layer, framed on the result's box. */
export function createRadarMap(container: HTMLElement, bbox: Bbox, layer: RadarLayer, { zoomButtons = false } = {}): MapLibreMap {
  const [w, s, e, n] = bbox;
  const map = new MapLibreMap({
    container,
    style: radarStyle(layer),
    bounds: [[w, s], [e, n]],
    fitBoundsOptions: { padding: 24 },
    attributionControl: { compact: true },
    dragRotate: false,
    pitchWithRotate: false,
  });
  if (zoomButtons) map.addControl(new NavigationControl({ showCompass: false }), "top-right");
  return map;
}

// ---------------------------------------------------------------- numbers and labels

export interface SensorTotals {
  /** Whole-patch hectares labeled NISAR majority or both/mixed; not exact flagged-block area. */
  nisar: number;
  /** Whole-patch hectares labeled Sentinel-1 majority or both/mixed; not exact flagged-block area. */
  s1: number;
  onlyNisar: number;
  onlyS1: number;
  both: number;
}

export function sensorTotals(areas: readonly ChangeArea[]): SensorTotals {
  const sum = (k: ChangeArea["agreement"]) => areas.reduce((t, a) => (a.agreement === k ? t + a.area_ha : t), 0);
  const onlyNisar = sum("L");
  const onlyS1 = sum("C");
  const both = sum("both");
  return { nisar: onlyNisar + both, s1: onlyS1 + both, onlyNisar, onlyS1, both };
}

export const formatHa = (ha: number) => `${Math.round(ha).toLocaleString("en-US")} ha`;

/** "Jul 13, 2026" for an ISO date or UTC datetime; null when missing or unparseable. */
export function formatPass(date: IsoDate | undefined): string | null {
  const t = date ? Date.parse(date) : NaN;
  if (Number.isNaN(t)) return null;
  return new Date(t).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

// ---------------------------------------------------------------- two maps, one camera

type Syncable = Pick<MapLibreMap, "on" | "off" | "getCenter" | "getZoom" | "getBearing" | "getPitch" | "jumpTo">;

/** Keep two maps on the same camera. Returns a function that stops syncing. */
export function syncMaps(a: Syncable, b: Syncable): () => void {
  let syncing = false;
  const follow = (src: Syncable, dst: Syncable) => () => {
    if (syncing) return; // dst.jumpTo fires dst's own "move"; don't bounce it back
    syncing = true;
    try {
      dst.jumpTo({ center: src.getCenter(), zoom: src.getZoom(), bearing: src.getBearing(), pitch: src.getPitch() });
    } finally {
      syncing = false;
    }
  };
  const onA = follow(a, b);
  const onB = follow(b, a);
  a.on("move", onA);
  b.on("move", onB);
  return () => {
    a.off("move", onA);
    b.off("move", onB);
  };
}

// ---------------------------------------------------------------- swipe control

/** The part of @maplibre/maplibre-gl-compare's Compare that the swipe uses. */
export interface CompareControl {
  setSlider(x: number): void;
  on(type: "slideend", fn: (e: { currentPosition: number }) => void): CompareControl;
  remove(): void;
}

export type CompareCtor = new (
  a: MapLibreMap,
  b: MapLibreMap,
  container: HTMLElement,
  options?: { orientation?: "vertical" | "horizontal"; mousemove?: boolean },
) => CompareControl;

/** The browser events dependency lets Vite bundle the library's normal module entry. */
export function loadCompare(): Promise<CompareCtor> {
  return Promise.resolve(Compare);
}

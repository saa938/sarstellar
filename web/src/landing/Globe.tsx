import { useEffect, useRef } from "react";
import type { Map as MLMap, GeoJSONSource } from "maplibre-gl";
import { maplibregl, GIBS_ATTR, GIBS_BLACK_MARBLE } from "../lib/maplibre";
import type { StageIndexEntry } from "../lib/types";
import { prefersReducedMotion } from "../stage/clock";

interface Props {
  stages: StageIndexEntry[];
  /** fraction of the container's smaller side used by the globe radius */
  fill?: number;
  spin?: boolean;
  startLng?: number;
  lat?: number;
  onReady?: () => void;
  focus?: [number, number] | null;
  attribution?: boolean;
}

/** A slowly turning night globe (NASA GIBS VIIRS Black Marble) with the stages pulsing on the beat. */
export default function Globe({ stages, fill = 0.4, spin = true, startLng = -40, lat = 12, onReady, focus = null, attribution = true }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const focusRef = useRef(focus);
  focusRef.current = focus;

  useEffect(() => {
    if (!el.current) return;
    const zoomFor = () => {
      const r = el.current!.getBoundingClientRect();
      const radius = Math.max(60, Math.min(r.width, r.height) * fill);
      return Math.log2(radius / 81.5);
    };
    const fc = {
      type: "FeatureCollection" as const,
      features: stages.map((s) => ({ type: "Feature" as const, properties: { id: s.id, move: s.move }, geometry: { type: "Point" as const, coordinates: s.center } })),
    };
    const map = new maplibregl.Map({
      container: el.current,
      style: {
        version: 8,
        projection: { type: "globe" },
        sky: {
          "sky-color": "#06070b",
          "horizon-color": "#203a66",
          "fog-color": "#06070b",
          "atmosphere-blend": 0.9,
        },
        sources: {
          night: { type: "raster", tiles: [GIBS_BLACK_MARBLE], tileSize: 256, maxzoom: 8, attribution: GIBS_ATTR },
          stages: { type: "geojson", data: fc },
        },
        layers: [
          { id: "bg", type: "background", paint: { "background-color": "#06070b" } },
          { id: "night", type: "raster", source: "night", paint: { "raster-brightness-max": 1, "raster-contrast": 0.12, "raster-saturation": -0.1, "raster-fade-duration": 400 } },
          { id: "halo", type: "circle", source: "stages", paint: { "circle-radius": 16, "circle-color": "#f2d08a", "circle-opacity": 0.16, "circle-blur": 1, "circle-pitch-alignment": "map" } },
          { id: "ring", type: "circle", source: "stages", paint: { "circle-radius": 6, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#f7e3b5", "circle-stroke-width": 1.2, "circle-stroke-opacity": 0.7, "circle-pitch-alignment": "map" } },
          { id: "core", type: "circle", source: "stages", paint: { "circle-radius": 2.8, "circle-color": "#fff4d6", "circle-pitch-alignment": "map" } },
        ],
      },
      center: [startLng, lat],
      zoom: 1.5,
      interactive: false,
      attributionControl: attribution ? { compact: true } : false,
      fadeDuration: 0,
    });
    mapRef.current = map;
    const fit = () => map.setZoom(zoomFor());
    fit();
    const ro = new ResizeObserver(() => {
      map.resize();
      if (!focusRef.current) fit();
    });
    ro.observe(el.current);
    // reveal as soon as the style is up; tiles stream in underneath
    let revealed = false;
    const reveal = () => {
      if (revealed) return;
      revealed = true;
      onReady?.();
    };
    map.once("style.load", () => setTimeout(reveal, 350));
    map.once("load", reveal);
    const fallback = setTimeout(reveal, 2500);

    let raf = 0;
    let lng = startLng;
    const reduced = prefersReducedMotion();
    const t0 = performance.now();
    const tick = (now: number) => {
      const t = (now - t0) / 1000;
      if (spin && !reduced && !focusRef.current) {
        lng += 0.045;
        if (lng > 180) lng -= 360;
        map.jumpTo({ center: [lng, lat] });
      }
      // all stages pulse together on a 1.2 s beat, like passes arriving
      const phase = (t % 1.2) / 1.2;
      const e = 1 - Math.pow(1 - phase, 3);
      if (map.getLayer("ring")) {
        map.setPaintProperty("ring", "circle-radius", 4 + e * 16);
        map.setPaintProperty("ring", "circle-stroke-opacity", 0.75 * (1 - phase));
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      clearTimeout(fallback);
      cancelAnimationFrame(raf);
      ro.disconnect();
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const src = map.getSource("stages") as GeoJSONSource | undefined;
    src?.setData({
      type: "FeatureCollection",
      features: stages.map((s) => ({ type: "Feature", properties: { id: s.id, move: s.move }, geometry: { type: "Point", coordinates: s.center } })),
    });
  }, [stages]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !focus) return;
    map.flyTo({ center: focus, zoom: 4.2, duration: 2600, essential: true });
  }, [focus]);

  return <div ref={el} className="globe" />;
}

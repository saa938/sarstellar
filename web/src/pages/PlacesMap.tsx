import { useEffect, useMemo, useRef, useState } from "react";
import type { Map as MLMap, GeoJSONSource, MapOptions } from "maplibre-gl";
import { maplibregl, DARK_ATTR, DARK_BASE, DARK_LABELS } from "../lib/maplibre";
import { loadStage } from "../lib/data";
import type { LonLat, StageIndexEntry } from "../lib/types";
import "./PlacesMap.css";

type BBox = [number, number, number, number]; // west, south, east, north
type Style = Exclude<MapOptions["style"], string | undefined>;

interface Shape {
  id: string;
  name: string;
  center: LonLat;
  bbox: BBox | null; // null: the stage file has no usable bbox, so the place is drawn as a marker only
}

interface Props {
  stages: StageIndexEntry[];
  /** the place highlighted from the list (hover or focus): the map highlights it and flies there */
  activeId: string | null;
  /** a click on a place: same as clicking its card in the list */
  onOpen: (id: string) => void;
}

// NISAR is amber everywhere on this site; every place here is a stack of NISAR passes.
const AMBER = "#f59e0b";
const HIT_LAYERS = ["area-fill", "pin"];

const finite = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);

function validBBox(b: unknown): BBox | null {
  if (!Array.isArray(b) || b.length !== 4 || !b.every(finite)) return null;
  return b[0] < b[2] && b[1] < b[3] && Math.abs(b[1]) <= 90 && Math.abs(b[3]) <= 90 ? (b as BBox) : null;
}

/** The index only carries each place's center; the bbox lives in its stage.json, so it joins in after it loads. */
function useShapes(stages: StageIndexEntry[]): Shape[] {
  const [boxes, setBoxes] = useState<Record<string, BBox>>({});
  useEffect(() => {
    let dead = false;
    Promise.all(
      stages.map((s) =>
        loadStage(s.id)
          .then((r) => [s.id, validBBox(r?.meta.bbox)] as const)
          .catch(() => [s.id, null] as const),
      ),
    ).then((all) => {
      if (dead) return;
      const next: Record<string, BBox> = {};
      for (const [id, b] of all) if (b) next[id] = b;
      setBoxes(next);
    });
    return () => {
      dead = true;
    };
  }, [stages]);
  return useMemo(
    () =>
      stages
        .filter((s) => Array.isArray(s.center) && finite(s.center[0]) && finite(s.center[1]))
        .map((s) => ({ id: s.id, name: s.name, center: s.center, bbox: boxes[s.id] ?? null })),
    [stages, boxes],
  );
}

function areasFC(shapes: Shape[]) {
  return {
    type: "FeatureCollection" as const,
    features: shapes.flatMap((s) => {
      if (!s.bbox) return [];
      const [w, so, e, n] = s.bbox;
      return [
        {
          type: "Feature" as const,
          properties: { id: s.id },
          geometry: { type: "Polygon" as const, coordinates: [[[w, so], [e, so], [e, n], [w, n], [w, so]]] },
        },
      ];
    }),
  };
}

function pinsFC(shapes: Shape[]) {
  return {
    type: "FeatureCollection" as const,
    features: shapes.map((s) => ({ type: "Feature" as const, properties: { id: s.id }, geometry: { type: "Point" as const, coordinates: s.center } })),
  };
}

function buildStyle(shapes: Shape[]): Style {
  return {
    version: 8,
    sources: {
      base: { type: "raster", tiles: DARK_BASE, tileSize: 256, maxzoom: 14, attribution: DARK_ATTR },
      labels: { type: "raster", tiles: DARK_LABELS, tileSize: 256, maxzoom: 14 },
      areas: { type: "geojson", data: areasFC(shapes) },
      pins: { type: "geojson", data: pinsFC(shapes) },
    },
    layers: [
      { id: "bg", type: "background", paint: { "background-color": "#06070b" } },
      { id: "base", type: "raster", source: "base", paint: { "raster-brightness-max": 0.8, "raster-fade-duration": 200 } },
      { id: "labels", type: "raster", source: "labels", paint: { "raster-brightness-max": 0.8, "raster-fade-duration": 200 } },
      { id: "area-fill", type: "fill", source: "areas", paint: { "fill-color": AMBER, "fill-opacity": 0.12 } },
      { id: "area-line", type: "line", source: "areas", paint: { "line-color": AMBER, "line-width": 1.5 } },
      { id: "pin-halo", type: "circle", source: "pins", paint: { "circle-radius": 12, "circle-color": AMBER, "circle-opacity": 0.2, "circle-blur": 0.8 } },
      { id: "pin", type: "circle", source: "pins", paint: { "circle-radius": 5.5, "circle-color": AMBER, "circle-stroke-color": "#06070b", "circle-stroke-width": 1.5 } },
    ],
  };
}

/** Thicker outline, brighter fill and a bigger dot for one place. A no-op until the style has loaded. */
function highlight(map: MLMap, id: string | null) {
  if (!map.getLayer("area-fill")) return;
  const on: ["==", ["get", string], string] = ["==", ["get", "id"], id ?? ""];
  map.setPaintProperty("area-fill", "fill-opacity", ["case", on, 0.4, 0.12]);
  map.setPaintProperty("area-line", "line-width", ["case", on, 3, 1.5]);
  map.setPaintProperty("pin", "circle-radius", ["case", on, 8, 5.5]);
}

/** Returns false when there is nothing to fit yet (no places, or the container has no size). */
function fitAll(map: MLMap, shapes: Shape[], duration: number): boolean {
  if (!shapes.length || !map.getContainer().clientWidth) return false;
  const b = new maplibregl.LngLatBounds();
  for (const s of shapes) {
    if (s.bbox) {
      b.extend([s.bbox[0], s.bbox[1]]);
      b.extend([s.bbox[2], s.bbox[3]]);
    } else b.extend(s.center);
  }
  map.fitBounds(b, { padding: 36, maxZoom: 6, duration });
  return true;
}

function flyToShape(map: MLMap, s: Shape) {
  const cam = s.bbox
    ? map.cameraForBounds(
        [
          [s.bbox[0], s.bbox[1]],
          [s.bbox[2], s.bbox[3]],
        ],
        { padding: 48, maxZoom: 9 },
      )
    : undefined;
  map.flyTo({ center: cam?.center ?? s.center, zoom: cam?.zoom ?? 7, duration: 1100 });
}

/** Every place on one map: its bbox as an amber outline, plus a dot. Hover for the name, click to open it. */
export default function PlacesMap({ stages, activeId, onOpen }: Props) {
  const shapes = useShapes(stages);
  const el = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const [failed, setFailed] = useState(false);
  const shapesRef = useRef(shapes);
  shapesRef.current = shapes;
  const activeRef = useRef(activeId);
  activeRef.current = activeId;
  const openRef = useRef(onOpen);
  openRef.current = onOpen;
  const hoverRef = useRef<string | null>(null);
  const fittedRef = useRef(false);

  useEffect(() => {
    const node = el.current;
    if (!node) return;
    let map: MLMap;
    try {
      map = new maplibregl.Map({
        container: node,
        style: buildStyle(shapesRef.current),
        center: [10, 25],
        zoom: 1,
        maxZoom: 12,
        dragRotate: false,
        pitchWithRotate: false,
        // on a phone one finger scrolls the page; two fingers move the map
        cooperativeGestures: !!window.matchMedia?.("(pointer: coarse)").matches,
        attributionControl: { compact: true },
      });
    } catch {
      // no WebGL (a test environment, a locked-down browser): the list below carries the page on its own
      setFailed(true);
      return;
    }
    mapRef.current = map;
    fittedRef.current = false;
    hoverRef.current = null;
    let alive = true;
    map.touchZoomRotate.disableRotation();
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12, className: "placesmap__tip" });
    const hit = (pt: { x: number; y: number }) => {
      // a few pixels of slack so a fingertip can find a small dot
      const f = map.queryRenderedFeatures(
        [
          [pt.x - 8, pt.y - 8],
          [pt.x + 8, pt.y + 8],
        ],
        { layers: HIT_LAYERS },
      )[0];
      const id = f?.properties?.id;
      return typeof id === "string" ? id : null;
    };
    const setHover = (id: string | null) => {
      if (id === hoverRef.current) return;
      hoverRef.current = id;
      const s = id ? shapesRef.current.find((x) => x.id === id) : undefined;
      if (s) popup.setLngLat(s.center).setText(s.name).addTo(map);
      else popup.remove();
      map.getCanvas().style.cursor = s ? "pointer" : "";
      highlight(map, id ?? activeRef.current);
    };
    map.on("mousemove", (e) => alive && setHover(hit(e.point)));
    map.on("mouseout", () => alive && setHover(null));
    map.on("click", (e) => {
      if (!alive) return;
      const id = hit(e.point);
      if (id) openRef.current(id);
    });
    map.on("load", () => {
      if (!alive) return;
      (map.getSource("areas") as GeoJSONSource | undefined)?.setData(areasFC(shapesRef.current));
      (map.getSource("pins") as GeoJSONSource | undefined)?.setData(pinsFC(shapesRef.current));
      highlight(map, hoverRef.current ?? activeRef.current);
    });
    const ro = new ResizeObserver(() => {
      if (alive) map.resize();
    });
    ro.observe(node);

    return () => {
      alive = false;
      ro.disconnect();
      popup.remove();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // bboxes arriving after the first paint redraw the outlines; the first non-empty list fits the view
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !shapes.length) return;
    (map.getSource("areas") as GeoJSONSource | undefined)?.setData(areasFC(shapes));
    (map.getSource("pins") as GeoJSONSource | undefined)?.setData(pinsFC(shapes));
    if (!fittedRef.current) fittedRef.current = fitAll(map, shapes, 0);
  }, [shapes]);

  // a place picked in the list: highlight it, then fly there once the pointer has settled
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    highlight(map, hoverRef.current ?? activeId);
    if (!activeId) return;
    const t = window.setTimeout(() => {
      const s = shapesRef.current.find((x) => x.id === activeId);
      if (s && mapRef.current === map) flyToShape(map, s);
    }, 220);
    return () => clearTimeout(t);
  }, [activeId]);

  if (failed) return null;
  return (
    <div className="placesmap" role="region" aria-label="Map of the places NISAR watched. The cards below list the same places.">
      <div ref={el} className="placesmap__map" />
      <button type="button" className="placesmap__all" onClick={() => mapRef.current && fitAll(mapRef.current, shapesRef.current, 700)}>
        Show all places
      </button>
    </div>
  );
}

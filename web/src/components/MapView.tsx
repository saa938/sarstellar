import "../pages/maplibreWorker.ts";
import { Map, NavigationControl, type GeoJSONSource } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
import type { Agreement, Result } from "../types.ts";
import { AREA_COLORS, agreementFilter, areaFeatures, createBasemapStyle, selectionFilter } from "./mapModel.ts";
import "./MapView.css";

export interface MapViewProps {
  result: Result | null;
  visible: Record<Agreement, boolean>;
  selectedAreaId: string | null;
  opacity?: number;
  onSelectArea: (id: string) => void;
  onMapReady?: (map: Map | null) => void;
}

const SOURCE = "sarstellar-areas";
const FILL = "sarstellar-area-fill";
const OUTLINE = "sarstellar-area-outline";
const START_ERROR = "The map could not start. Check that WebGL is enabled in your browser. Findings remain available in the list.";
const LOAD_ERROR = "Some map imagery could not load. Findings remain available in the list.";

/** A single persistent map. React updates its data and filters without replacing the WebGL canvas. */
export default function MapView(props: MapViewProps) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);
  const loaded = useRef(false);
  const displayed = useRef<Result | null>(null);
  const latest = useRef(props);
  latest.current = props;
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  function synchronize(map: Map) {
    const { result, visible, selectedAreaId, opacity = 0.65 } = latest.current;
    (map.getSource(SOURCE) as GeoJSONSource).setData(areaFeatures(result));
    map.setFilter(FILL, agreementFilter(visible));
    map.setFilter(OUTLINE, selectionFilter(visible, selectedAreaId));
    map.setPaintProperty(FILL, "fill-opacity", opacity);

    if (result) {
      // Show the selectable >=3 ha areas. The exported agreement PNG also contains small,
      // unlabelled blocks, which must not appear as findings that cannot be inspected.
      if (displayed.current !== result) {
        const [w, s, e, n] = result.bbox;
        map.fitBounds([[w, s], [e, n]], { padding: 44, maxZoom: 13.5, duration: 0 });
      }
    }
    displayed.current = result;
  }

  useEffect(() => {
    if (!container.current) return;
    let map: Map;
    let disposed = false;
    setReady(false);
    setError(null);
    loaded.current = false;
    displayed.current = null;
    try {
      map = new Map({
        container: container.current,
        style: createBasemapStyle(),
        center: [-100, 39], zoom: 3.2,
        attributionControl: { compact: true },
      });
    } catch {
      setError(START_ERROR);
      return;
    }
    mapRef.current = map;
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");

    const load = () => {
      if (disposed) return;
      map.addSource(SOURCE, { type: "geojson", data: areaFeatures(null) });
      map.addLayer({
        id: FILL, type: "fill", source: SOURCE,
        paint: {
          "fill-color": AREA_COLORS,
          "fill-opacity": 0.55,
          "fill-outline-color": AREA_COLORS,
        },
      });
      map.addLayer({
        id: OUTLINE, type: "line", source: SOURCE,
        filter: ["==", ["get", "id"], ""],
        paint: { "line-color": "#ffffff", "line-width": 2.5, "line-opacity": 0.95 },
      });
      loaded.current = true;
      synchronize(map);
      setReady(true);
      latest.current.onMapReady?.(map);
    };
    const select = (event: { features?: { properties?: Record<string, unknown> | null }[] }) => {
      const id = event.features?.[0]?.properties?.id;
      if (typeof id === "string") latest.current.onSelectArea(id);
    };
    const enter = () => { map.getCanvas().style.cursor = "pointer"; };
    const leave = () => { map.getCanvas().style.cursor = ""; };
    const fail = () => { if (!disposed) setError(LOAD_ERROR); };
    const contextLost = () => {
      if (!disposed) setError("Map graphics were interrupted. Findings remain available in the list.");
    };
    const contextRestored = () => { if (!disposed) setError(null); };
    map.on("load", load);
    map.on("error", fail);
    map.on("click", FILL, select);
    map.on("mouseenter", FILL, enter);
    map.on("mouseleave", FILL, leave);
    const canvas = map.getCanvas();
    canvas.addEventListener("webglcontextlost", contextLost);
    canvas.addEventListener("webglcontextrestored", contextRestored);
    const observer = typeof ResizeObserver !== "undefined"
      ? new ResizeObserver(() => { if (!disposed) map.resize(); }) : null;
    observer?.observe(container.current);
    const resize = () => { if (!disposed) map.resize(); };
    window.addEventListener("resize", resize);

    return () => {
      disposed = true;
      observer?.disconnect();
      window.removeEventListener("resize", resize);
      canvas.removeEventListener("webglcontextlost", contextLost);
      canvas.removeEventListener("webglcontextrestored", contextRestored);
      map.off("load", load);
      map.off("error", fail);
      map.off("click", FILL, select);
      map.off("mouseenter", FILL, enter);
      map.off("mouseleave", FILL, leave);
      latest.current.onMapReady?.(null);
      map.remove();
      mapRef.current = null;
      loaded.current = false;
    };
  }, [attempt]);

  useEffect(() => {
    const map = mapRef.current;
    if (map && loaded.current) synchronize(map);
  }, [props.result, props.visible, props.selectedAreaId, props.opacity]);

  return (
    <div className="map-view" role="region" aria-label="Radar change map">
      <div className="map-view__canvas" ref={container} />
      {error ? (
        <div className="map-view__notice" role="status">
          <span>{error}</span>
          <button type="button" onClick={() => setAttempt((value) => value + 1)}>Retry map</button>
        </div>
      ) : !ready ? (
        <div className="map-view__notice" role="status">Loading satellite map…</div>
      ) : null}
    </div>
  );
}

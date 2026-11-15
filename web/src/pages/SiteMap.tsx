// Scorecard site map: one dot per site (box center), colored by train / held-out split, on muted imagery.
import type { FeatureCollection, Point } from "geojson";
import { Map as MapLibreMap, NavigationControl, Popup, type LngLatBoundsLike, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
import type { ScorecardSite } from "../types.ts";
import "./maplibreWorker.ts";
import { classLabel } from "./scorecardModel.ts";

/** Split colors stay out of the amber/violet/cyan agreement palette, which means "which radar saw it". */
export const SPLIT_COLORS = { train: "#8b95ab", holdout: "#34d399" } as const;

const ESRI_IMAGERY = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";

const STYLE: StyleSpecification = {
  version: 8,
  sources: {
    imagery: {
      type: "raster",
      tiles: [ESRI_IMAGERY],
      tileSize: 256,
      maxzoom: 18,
      attribution: "Imagery: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
    },
  },
  layers: [
    {
      id: "imagery",
      type: "raster",
      source: "imagery",
      paint: { "raster-saturation": -0.6, "raster-brightness-max": 0.55 },
    },
  ],
};

interface SiteProps {
  id: string;
  kind: string;
  state: string;
  split: "train" | "holdout";
}

function validSites(sites: ScorecardSite[]): ScorecardSite[] {
  return sites.filter((s) => Array.isArray(s.bbox) && s.bbox.length === 4 && s.bbox.every(Number.isFinite));
}

export function sitesGeoJSON(sites: ScorecardSite[]): FeatureCollection<Point, SiteProps> {
  return {
    type: "FeatureCollection",
    features: validSites(sites).map(({ id, kind, state, split, bbox: [w, s, e, n] }) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [(w + e) / 2, (s + n) / 2] },
      properties: { id, kind, state, split: split === "holdout" ? "holdout" : "train" },
    })),
  };
}

/** Bounds covering every site box, or null when there are none. */
export function sitesBounds(sites: ScorecardSite[]): [[number, number], [number, number]] | null {
  const ok = validSites(sites);
  if (ok.length === 0) return null;
  const ws = ok.map((s) => s.bbox);
  return [
    [Math.min(...ws.map((b) => b[0])), Math.min(...ws.map((b) => b[1]))],
    [Math.max(...ws.map((b) => b[2])), Math.max(...ws.map((b) => b[3]))],
  ];
}

export default function SiteMap({ sites }: { sites: ScorecardSite[] }) {
  const container = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const el = container.current;
    const bounds = sitesBounds(sites);
    if (!el || !bounds) return;
    let map: MapLibreMap;
    try {
      map = new MapLibreMap({
        container: el,
        style: STYLE,
        bounds: bounds as LngLatBoundsLike,
        fitBoundsOptions: { padding: 40, maxZoom: 9 },
        attributionControl: { compact: true },
        dragRotate: false,
      });
    } catch {
      setFailed(true); // e.g. no WebGL: the counts and legend above still tell the story
      return;
    }
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    const data = sitesGeoJSON(sites);
    map.on("load", () => {
      map.addSource("sites", { type: "geojson", data });
      map.addLayer({
        id: "sites",
        type: "circle",
        source: "sites",
        paint: {
          "circle-radius": 5,
          "circle-color": ["match", ["get", "split"], "holdout", SPLIT_COLORS.holdout, SPLIT_COLORS.train],
          "circle-stroke-color": "#0b0f17",
          "circle-stroke-width": 1,
        },
      });
    });
    const popup = new Popup({ closeButton: false, closeOnClick: false, offset: 8 });
    map.on("mousemove", "sites", (e) => {
      const p = e.features?.[0]?.properties as SiteProps | undefined;
      if (!p) return;
      map.getCanvas().style.cursor = "pointer";
      const split = p.split === "holdout" ? "held-out state" : "training state";
      popup.setLngLat(e.lngLat).setText(`${p.state} · ${classLabel(p.kind)} · ${split}`).addTo(map);
    });
    map.on("mouseleave", "sites", () => {
      map.getCanvas().style.cursor = "";
      popup.remove();
    });
    return () => {
      popup.remove();
      map.remove();
    };
  }, [sites]);

  if (failed) return <div className="pg-sitemap pg-sitemap-off">The site map needs WebGL, which this browser has turned off.</div>;
  return <div className="pg-sitemap" ref={container} />;
}

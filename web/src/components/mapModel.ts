import type { ExpressionSpecification, StyleSpecification } from "maplibre-gl";
import { AGREEMENT_COLORS, type Agreement, type Result } from "../types.ts";

/** No API key is required. Each map gets its own style object and sources. */
export function createBasemapStyle(): StyleSpecification {
  return {
    version: 8,
    sources: {
      satellite: {
        type: "raster",
        tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
        tileSize: 256,
        maxzoom: 19,
        attribution: 'Imagery &copy; <a href="https://www.esri.com/">Esri</a>, Maxar, Earthstar Geographics, and the GIS User Community',
      },
    },
    layers: [
      { id: "background", type: "background", paint: { "background-color": "#0b0f17" } },
      {
        id: "satellite-imagery", type: "raster", source: "satellite",
        paint: {
          "raster-saturation": -0.75,
          "raster-brightness-min": 0.05,
          "raster-brightness-max": 0.58,
          "raster-fade-duration": 200,
        },
      },
    ],
  };
}

export const AREA_COLORS: ExpressionSpecification = [
  "match", ["get", "agreement"],
  "L", AGREEMENT_COLORS.L, "both", AGREEMENT_COLORS.both, "C", AGREEMENT_COLORS.C,
  "#8b95ab",
];

export function areaFeatures(result: Result | null) {
  return {
    type: "FeatureCollection" as const,
    features: (result?.areas ?? []).map((area) => ({
      type: "Feature" as const,
      id: area.id,
      properties: { id: area.id, agreement: area.agreement, class: area.class },
      geometry: area.geometry,
    })),
  };
}

export function agreementFilter(visible: Record<Agreement, boolean>): ExpressionSpecification {
  const keys = (["L", "both", "C"] as const).filter((key) => visible[key]);
  // A literal array also handles the all-hidden case without an invalid empty `in` expression.
  return ["in", ["get", "agreement"], ["literal", keys]];
}

export function selectionFilter(
  visible: Record<Agreement, boolean>, selectedAreaId: string | null,
): ExpressionSpecification {
  return ["all", agreementFilter(visible), ["==", ["get", "id"], selectedAreaId ?? ""]];
}

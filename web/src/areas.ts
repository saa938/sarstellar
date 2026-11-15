// Pure helpers for a Result's change areas: legend labels and hectare sums, the area list, dates, and the
// map's GeoJSON and filters. Class titles and per-area wording live in components/changeFormat.ts (B3).
import type { Agreement, ChangeArea, GeoMultiPolygon, GeoPolygon, IsoDate } from "./types.ts";

/** Legend order, as in the mockup. */
export const AGREEMENTS: readonly Agreement[] = ["L", "both", "C"];

export const AGREEMENT_LABELS: Record<Agreement, string> = {
  L: "Only NISAR saw it",
  both: "Both satellites saw it",
  C: "Only Sentinel-1 saw it",
};

/** A live box can return 200+ areas: the side panel lists this many, and the rest stay on the map only. */
export const AREA_LIST_LIMIT = 25;

export function hectareSums(areas: readonly ChangeArea[]): Record<Agreement, number> {
  const sums: Record<Agreement, number> = { L: 0, both: 0, C: 0 };
  for (const a of areas) sums[a.agreement] += a.area_ha;
  return sums;
}

const bySizeDesc = (x: ChangeArea, y: ChangeArea) => y.area_ha - x.area_ha;

/** The largest areas, largest first, capped at AREA_LIST_LIMIT. */
export function largestAreas(areas: readonly ChangeArea[], limit = AREA_LIST_LIMIT): ChangeArea[] {
  return [...areas].sort(bySizeDesc).slice(0, limit);
}

function utcParts(iso: IsoDate): { md: string; year: number } {
  const d = new Date(iso);
  return { md: d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" }), year: d.getUTCFullYear() };
}

/** "Jul 13 – Sep 11, 2026" (or "Dec 1, 2025 – Jan 10, 2026" across years) from the first and last dates. */
export function formatDateRange(dates: readonly IsoDate[]): string {
  if (dates.length === 0) return "";
  const a = utcParts(dates[0]);
  const b = utcParts(dates[dates.length - 1]);
  if (a.md === b.md && a.year === b.year) return `${a.md}, ${a.year}`;
  return a.year === b.year ? `${a.md} – ${b.md}, ${b.year}` : `${a.md}, ${a.year} – ${b.md}, ${b.year}`;
}

export interface AreaFeature {
  type: "Feature";
  properties: { id: string; agreement: Agreement };
  geometry: GeoPolygon | GeoMultiPolygon;
}

export interface AreaFeatureCollection {
  type: "FeatureCollection";
  features: AreaFeature[];
}

/** Every area as GeoJSON, largest first so small areas draw on top and stay clickable. */
export function areasToGeoJSON(areas: readonly ChangeArea[]): AreaFeatureCollection {
  return {
    type: "FeatureCollection",
    features: [...areas]
      .sort(bySizeDesc)
      .map((a) => ({ type: "Feature", properties: { id: a.id, agreement: a.agreement }, geometry: a.geometry })),
  };
}

/** MapLibre filter that drops features whose agreement is hidden in the legend. */
export function visibleFilter(hidden: ReadonlySet<Agreement>): ["!", ["in", ["get", "agreement"], ["literal", Agreement[]]]] {
  return ["!", ["in", ["get", "agreement"], ["literal", AGREEMENTS.filter((k) => hidden.has(k))]]];
}

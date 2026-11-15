// Box geometry and the client-side box rules (plan "Global Constraints": w < e, s < n, inside the US
// bounds, each side <= 20 km). The API enforces the same rules with HTTP 422; checking here means an
// oversize box is never submitted.
import type { Bbox } from "../types.ts";

export const MAX_SIDE_KM = 20;
export const OVERSIZE_MESSAGE = "Boxes are limited to 20 km a side.";
export const OUTSIDE_US_MESSAGE = "Live analysis covers the United States only. Draw the box inside the US.";
export const EMPTY_BOX_MESSAGE = "Click two opposite corners to draw a box.";

/** Lon/lat limits for live boxes. */
export const US_BOUNDS = { west: -180, south: 17, east: -60, north: 72 } as const;

const EARTH_RADIUS_KM = 6371.0088;
const RAD = Math.PI / 180;

export interface BoxSize {
  widthKm: number;
  heightKm: number;
  areaKm2: number;
}

/**
 * Side lengths on a sphere. Width is the arc along the edge nearer the equator (the longer of the two
 * east-west edges), so a box that passes here can't be over the limit on any edge.
 */
export function boxSize([w, s, e, n]: Bbox): BoxSize {
  const dLon = (e - w) * RAD;
  const minAbsLat = s <= 0 && n >= 0 ? 0 : Math.min(Math.abs(s), Math.abs(n));
  const widthKm = EARTH_RADIUS_KM * dLon * Math.cos(minAbsLat * RAD);
  const heightKm = EARTH_RADIUS_KM * (n - s) * RAD;
  const areaKm2 = EARTH_RADIUS_KM ** 2 * dLon * Math.abs(Math.sin(n * RAD) - Math.sin(s * RAD));
  return { widthKm, heightKm, areaKm2 };
}

/** The first rule a box breaks, as a readable message, or null when it can be submitted. */
export function validateBox(bbox: Bbox): string | null {
  const [w, s, e, n] = bbox;
  if (!bbox.every(Number.isFinite) || w >= e || s >= n) return EMPTY_BOX_MESSAGE;
  if (w < US_BOUNDS.west || e > US_BOUNDS.east || s < US_BOUNDS.south || n > US_BOUNDS.north) {
    return OUTSIDE_US_MESSAGE;
  }
  const { widthKm, heightKm } = boxSize(bbox);
  if (widthKm > MAX_SIDE_KM || heightKm > MAX_SIDE_KM) return OVERSIZE_MESSAGE;
  return null;
}

/** [w, s, e, n] of a polygon ring (positions [lon, lat]), rounded to 1e-6° (~0.1 m). */
export function bboxFromRing(ring: readonly (readonly number[])[]): Bbox {
  const lons = ring.map((p) => p[0]);
  const lats = ring.map((p) => p[1]);
  const r = (x: number) => Math.round(x * 1e6) / 1e6;
  return [r(Math.min(...lons)), r(Math.min(...lats)), r(Math.max(...lons)), r(Math.max(...lats))];
}

/** "7.6 × 5.6 km · 42 km²" */
export function formatSize({ widthKm, heightKm, areaKm2 }: BoxSize): string {
  const area = areaKm2 < 10 ? areaKm2.toFixed(1) : Math.round(areaKm2).toLocaleString("en-US");
  return `${widthKm.toFixed(1)} × ${heightKm.toFixed(1)} km · ${area} km²`;
}

/** Called while a box is drawn (done = false) and once when it is finished (done = true). */
export type BoxListener = (bbox: Bbox | null, done: boolean) => void;

/** What DrawBox needs from a drawing tool; the default is terra-draw on the MapLibre map. */
export interface BoxDrawer {
  /** Remove any previous box and enter rectangle drawing. */
  start(listener: BoxListener): void;
  /** Leave drawing mode and remove the box from the map. */
  clear(): void;
  /** Detach from the map. */
  destroy(): void;
}

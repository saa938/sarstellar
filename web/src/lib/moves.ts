// One color per move. Checked with the dataviz validator on the night surface (#06070b):
// the moves that share a stage (fall + scorch; vanish + bounce + waltz) clear the all-pairs
// CVD and normal-vision floors. Every use of color also carries a text label.

export const MOVE_IDS = ["still", "fall", "scorch", "bounce", "vanish", "waltz", "shimmer", "melt"] as const;
export type MoveId = (typeof MOVE_IDS)[number];

export const MOVE_COLORS: Record<string, string> = {
  still: "#a9a69c",
  fall: "#dfa200",
  scorch: "#e8504a",
  bounce: "#d55181",
  vanish: "#3987e5",
  waltz: "#0ca30c",
  shimmer: "#9085e9",
  melt: "#2fb3c9",
};

export const MOVE_NAMES: Record<string, string> = {
  still: "The Stillness",
  fall: "The Fall",
  scorch: "The Scorch",
  bounce: "The Bounce",
  vanish: "The Vanish",
  waltz: "The Waltz",
  shimmer: "The Shimmer",
  melt: "The Melt",
};

export const MOVE_VERBS: Record<string, string> = {
  still: "stands still",
  fall: "falls",
  scorch: "scorches",
  bounce: "bounces",
  vanish: "vanishes",
  waltz: "waltzes",
  shimmer: "shimmers",
  melt: "melts",
};

export const POL_COLORS = { HH: "#ffb38a", HV: "#7fd1c7" } as const;

/** Faint zone tints for the floor background, and starlight tints for dots by starting zone. */
export const ZONE_TINTS: Record<string, string> = {
  water: "#2a5fa8",
  soil: "#8a6a44",
  crops: "#7d8f37",
  forest: "#2f8f58",
  bounce: "#a3407f",
};

export const ZONE_STARLIGHT: Record<string, string> = {
  water: "#9dbcff",
  soil: "#f0d2ae",
  crops: "#e6efb0",
  forest: "#a8efc0",
  bounce: "#ffb3e2",
};

export function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function moveColor(id: string | undefined | null) {
  return (id && MOVE_COLORS[id]) || MOVE_COLORS.still;
}

import type { FloorSpec } from "./types";

/** Used only if moves.json cannot be loaded at all (same values as the contract example). */
export const DEFAULT_FLOOR: FloorSpec = {
  x: { pol: "HH", min: -30, max: 5 },
  y: { pol: "HV", min: -38, max: -5 },
  zones: [
    { id: "water", label: "Open water", center: [-24, -32] },
    { id: "soil", label: "Bare soil", center: [-13, -25] },
    { id: "crops", label: "Grass and crops", center: [-10, -19] },
    { id: "forest", label: "Forest", center: [-7, -13] },
    { id: "bounce", label: "Double bounce: flooded forest, cities", center: [0, -11] },
  ],
};

export function lighten(rgb: [number, number, number], amt: number): [number, number, number] {
  return [rgb[0] + (255 - rgb[0]) * amt, rgb[1] + (255 - rgb[1]) * amt, rgb[2] + (255 - rgb[2]) * amt];
}

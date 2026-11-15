// Scientific names for what the model recognizes (no dance names in the UI).

export const CHANGE_LABEL: Record<string, string> = {
  still: "No change",
  fall: "Forest loss",
  scorch: "Fire",
  bounce: "Flood under vegetation (double bounce)",
  vanish: "Open-water flood",
  waltz: "Crop growth and harvest",
  shimmer: "Soil wetting after rain",
  melt: "Ice surface change",
};

/** What the radar did, for "What changed here". */
export const CHANGE_NOTE: Record<string, string> = {
  fall: "the canopy echo (HV) dropped by several decibels within one pass",
  scorch: "HV fell across a wide, connected burned patch",
  bounce: "HH jumped while HV held still, the signature of water standing under plants",
  vanish: "both echoes went dark, because calm water reflects the pulse away",
  waltz: "HV climbed as the crop grew and fell back at harvest",
  melt: "HH changed as the ice surface melted and refroze",
  shimmer: "both echoes rose together for a pass after rain",
};

export const CHANGE_COLOR: Record<string, string> = {
  still: "#b9bccb",
  fall: "#dfa200",
  scorch: "#e8504a",
  bounce: "#d55181",
  vanish: "#3987e5",
  waltz: "#2fb24a",
  shimmer: "#9085e9",
  melt: "#2fb3c9",
};

export const AXIS_X = "HH: surface and bounce echo (dB)";
export const AXIS_Y = "HV: canopy (volume) echo (dB)";
export const DB_NOTE = "decibels: the radar's loudness scale; +3 dB is twice as loud";

export const REGIONS: { id: string; label: string; center: [number, number]; pos: "above" | "below" | "left" | "right" | "edge" }[] = [
  { id: "water", label: "open water", center: [-24, -32], pos: "above" },
  { id: "soil", label: "bare soil", center: [-13, -25], pos: "below" },
  { id: "crops", label: "crops", center: [-10, -19], pos: "left" },
  { id: "forest", label: "forest", center: [-7, -13], pos: "left" },
  { id: "bounce", label: "double bounce (cities, flooded trees, rice)", center: [0, -12], pos: "edge" },
];

export const REGION_TINT: Record<string, string> = {
  water: "42,95,168",
  soil: "138,106,68",
  crops: "125,143,55",
  forest: "47,143,88",
  bounce: "163,64,127",
};

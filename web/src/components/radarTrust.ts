// "Which radar should I trust?" for one change area, read from the held-out scorecard.
// Turns the benchmark's equal-recall precision into a per-area verdict: which radar saw the
// change, and which radar was the stronger detector for this cause on states the model never saw.
import type { ChangeArea, EqualRecallRow } from "../types.ts";

export type TrustTone = "agree" | "consistent" | "caution" | "none";

export interface TrustVerdict {
  tone: TrustTone;
  headline: string;
  detail: string;
}

type Sensor = "L" | "C";

/** Area cause classes that the held-out benchmark actually tested, mapped to its class names. */
const TESTED: Record<string, { row: string; label: string }> = {
  forest_loss: { row: "forest_loss", label: "forest loss" },
  burn: { row: "burn", label: "burn scars" },
  flood_open_water: { row: "flood_open_water", label: "open-water flooding" },
  crop_cycle: { row: "crop_cycle", label: "cultivated-land change" },
  harvest: { row: "crop_cycle", label: "cultivated-land change" },
};

const NAME: Record<Sensor, string> = { L: "NISAR", C: "Sentinel-1" };
/** Precision ratio either way that counts as "clearly better". */
const MARGIN = 1.25;

const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

function stronger(row: EqualRecallRow): Sensor | null {
  const { precision_L: l, precision_C: c } = row;
  if (!(l > 0) && !(c > 0)) return null;
  if (!(c > 0) || l / c >= MARGIN) return "L";
  if (!(l > 0) || c / l >= MARGIN) return "C";
  return null;
}

export function radarTrust(
  area: Pick<ChangeArea, "class" | "agreement">,
  rows: EqualRecallRow[] | undefined,
): TrustVerdict {
  const tested = TESTED[area.class];
  const row = tested && rows?.find((r) => r.class === tested.row);
  if (!tested || !row) {
    return {
      tone: "none",
      headline: "No held-out test covers this cause yet.",
      detail: "The benchmark tested forest loss, burn scars, open-water flooding and cultivated land.",
    };
  }
  const best = stronger(row);
  const fact = `On held-out states at ${Math.round(row.recall * 100)}% recall, ${tested.label} ` +
    `detections were ${pct(row.precision_L)} precise from NISAR and ${pct(row.precision_C)} from Sentinel-1.`;

  if (area.agreement === "both") {
    return {
      tone: "agree",
      headline: best
        ? `Both radars saw this. ${NAME[best]} is the specialist for ${tested.label}.`
        : `Both radars saw this; neither was clearly better for ${tested.label}.`,
      detail: fact,
    };
  }
  const saw: Sensor = area.agreement;
  const other: Sensor = saw === "L" ? "C" : "L";
  if (best === saw) {
    return {
      tone: "consistent",
      headline: `Only ${NAME[saw]} saw this, and ${NAME[saw]} is the specialist for ${tested.label}.`,
      detail: `${fact} Lean on ${NAME[saw]} here.`,
    };
  }
  if (best === other) {
    return {
      tone: "caution",
      headline: `Only ${NAME[saw]} saw this, but ${NAME[other]} is the stronger radar for ${tested.label}.`,
      detail: `${fact} Treat this as unconfirmed until checked.`,
    };
  }
  return {
    tone: "caution",
    headline: `Only ${NAME[saw]} saw this; neither radar was clearly better for ${tested.label}.`,
    detail: `${fact} Check an independent source.`,
  };
}

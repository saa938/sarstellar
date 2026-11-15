// Text and number formatting shared by ChangePanel, SeriesChart and Timeline (Task B3).
import { NISAR_GAP, type Agreement, type ChangeClass, type IsoDate } from "../types.ts";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MINUS = "−";
export const DAY_MS = 86_400_000;

export const GAP_START = Date.parse(NISAR_GAP.start);
export const GAP_END = Date.parse(NISAR_GAP.end);

/** Epoch ms; date-only strings ("2026-07-13") read as UTC midnight. NaN when unparseable. */
export function toTime(d: IsoDate): number {
  return Date.parse(d);
}

/** "Jul 13" (UTC, locale-independent). */
export function shortDate(t: number): string {
  const d = new Date(t);
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`;
}

/** "Jul 13, 2026" (UTC). */
export function longDate(t: number): string {
  return `${shortDate(t)}, ${new Date(t).getUTCFullYear()}`;
}

/** "Jul 27 – Aug 10, 2026": the permanent NISAR data gap. */
export const GAP_TEXT = `${shortDate(GAP_START)} – ${longDate(GAP_END)}`;

/** The part of the NISAR gap inside [t0, t1], or null when they don't overlap. */
export function gapWithin(t0: number, t1: number): [number, number] | null {
  const a = Math.max(t0, GAP_START);
  const b = Math.min(t1, GAP_END);
  return a < b ? [a, b] : null;
}

/** Indices to label so that labels sit at least `minGap` apart (positions ascending; first always kept). */
export function thinLabels(positions: number[], minGap: number): Set<number> {
  const keep = new Set<number>();
  let last = -Infinity;
  positions.forEach((p, i) => {
    if (p - last >= minGap) {
      keep.add(i);
      last = p;
    }
  });
  return keep;
}

export const CLASS_TITLES: Record<ChangeClass, string> = {
  forest_loss: "Forest loss",
  burn: "Burned area",
  flood_open_water: "Open-water flooding",
  flooded_vegetation: "Flooding under vegetation",
  crop_cycle: "Crop growth or harvest cycle",
  harvest: "Harvest",
  low_veg_loss: "Loss of low vegetation",
  soil_wetting: "Wetter soil",
  construction: "Construction",
  landslide: "Possible landslide",
  wet_snow: "Wet snow",
  uncertain: "Change, cause uncertain",
};

export function classTitle(cls: string): string {
  const title = CLASS_TITLES[cls as ChangeClass];
  if (title) return title;
  const words = cls.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export const AGREEMENT_TEXT: Record<Agreement, string> = {
  L: "Only NISAR saw this",
  both: "Both satellites saw this",
  C: "Only Sentinel-1 saw this",
};

/** Typographic minus sign in place of a leading hyphen. */
export function minus(s: string): string {
  return s.replace("-", MINUS);
}

/** Decimal places that keep a dB value readable: 1, or 2 for small values like 0.11. */
function dbDigits(v: number): number {
  return Math.abs(v) < 1 && Math.abs(v * 10 - Math.round(v * 10)) > 1e-9 ? 2 : 1;
}

/** A backscatter level, e.g. "−12.5". */
export function formatLevel(v: number): string {
  return minus(v.toFixed(1));
}

/** A number in `unit`; dB changes are signed ("+0.11", "−3.6"), other units plain ("1,284"). */
export function formatNumber(v: number, unit: string): string {
  if (unit === "dB") {
    const s = v.toFixed(dbDigits(v));
    return v > 0 && Number(s) !== 0 ? `+${s}` : minus(Number(s) === 0 ? s.replace("-", "") : s);
  }
  return minus(v.toLocaleString("en-US", { maximumFractionDigits: 2 }));
}

/** Appends the unit ("−3.6 dB", "40%"); no unit → the text alone. */
export function withUnit(text: string, unit: string): string {
  if (!unit) return text;
  return unit === "%" ? `${text}%` : `${text} ${unit}`;
}

export function formatP(p: number): string {
  if (!Number.isFinite(p) || p < 0) return "p not computed";
  if (p < 0.001) return "p < 0.001";
  return `p = ${Number(p.toPrecision(2))}`;
}

export function formatHa(v: number): string {
  return v.toLocaleString("en-US", { maximumFractionDigits: v < 10 ? 1 : 0 });
}

/** 1 → "1st", 12 → "12th", 22 → "22nd". */
export function ordinal(n: number): string {
  const tens = n % 100;
  const suffix = tens >= 11 && tens <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${suffix}`;
}

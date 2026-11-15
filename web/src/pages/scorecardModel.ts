// Pure logic behind the Scorecard page: the fusion headline, row grouping, labels and number formats.
// Kept free of React so the claims the page makes are unit-tested on their own.
import { AGREEMENT_COLORS, CHANGE_CLASSES, type Detector, type FusionRow, type Scorecard, type ScorecardClassRow } from "../types.ts";

/**
 * Metric drawn as bars per class. `classes[].ci_low/ci_high` are read as this metric's 95% bootstrap interval
 * (AUPRC, the same metric the fusion headline uses). If the scorecard batch puts the CI on F1 instead, change this.
 */
export const BAR_METRIC = "auprc" as const;
export const BAR_METRIC_LABEL = "AUPRC";

/** Display order: NISAR, NISAR degraded to 30 m, Sentinel-1, then the two fused detectors. */
export const DETECTORS: Detector[] = ["L", "L30", "C", "fused_fisher", "fused_bonferroni", "fused_logistic"];

interface DetectorInfo {
  label: string;
  color: string;
  /** Drawn at reduced opacity to tell variants apart while keeping the fixed color meaning. */
  dim: boolean;
}

const DETECTOR_INFO: Record<Detector, DetectorInfo> = {
  L: { label: "NISAR (L-band)", color: AGREEMENT_COLORS.L, dim: false },
  L30: { label: "NISAR at 30 m", color: AGREEMENT_COLORS.L, dim: true },
  C: { label: "Sentinel-1 (C-band)", color: AGREEMENT_COLORS.C, dim: false },
  fused_fisher: { label: "Both radars, Fisher fusion", color: AGREEMENT_COLORS.both, dim: false },
  fused_bonferroni: { label: "Both radars, Bonferroni fusion", color: AGREEMENT_COLORS.both, dim: false },
  fused_logistic: { label: "Both radars, logistic fusion", color: AGREEMENT_COLORS.both, dim: true },
  learned_L: { label: "Learned NISAR-only model", color: AGREEMENT_COLORS.L, dim: true },
  learned_C: { label: "Learned Sentinel-1-only model", color: AGREEMENT_COLORS.C, dim: true },
};

export function detectorInfo(d: string): DetectorInfo {
  return DETECTOR_INFO[d as Detector] ?? { label: d, color: "#8b95ab", dim: false };
}

const CLASS_LABELS: Record<string, string> = {
  forest_loss: "forest loss",
  flood_open_water: "open-water flood",
  flooded_vegetation: "flooded vegetation",
  crop_cycle: "cultivated land (proxy)",
  low_veg_loss: "low-vegetation loss",
  soil_wetting: "soil wetting",
  wet_snow: "wet snow",
  uncertain: "uncertain cause",
  stable: "stable ground",
};

/** Lower-case label for running text ("forest loss"). */
export function classLabel(cls: string): string {
  return CLASS_LABELS[cls] ?? cls.replace(/_/g, " ");
}

/** Sentence-case label for headings ("Forest loss"). */
export function classTitle(cls: string): string {
  const s = classLabel(cls);
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// ---------------------------------------------------------------- number formats

export function isNum(x: unknown): x is number {
  return typeof x === "number" && Number.isFinite(x);
}

const MINUS = "−";

/** Fixed decimals with a true minus sign; "—" for missing values. */
export function fmt(x: unknown, digits = 2): string {
  if (!isNum(x)) return "—";
  const s = x.toFixed(digits);
  return s.startsWith("-") ? MINUS + s.slice(1) : s;
}

export function signed(x: unknown, digits = 2): string {
  if (!isNum(x)) return "—";
  return x > 0 ? `+${fmt(x, digits)}` : fmt(x, digits);
}

/** A 0..1 fraction as a percentage. */
export function pct(x: unknown, digits = 1): string {
  return isNum(x) ? `${fmt(x * 100, digits)}%` : "—";
}

export function ratio(x: unknown): string {
  if (!isNum(x)) return "—";
  return `${x >= 10 ? x.toFixed(0) : x >= 1 ? x.toFixed(1) : x.toFixed(2)}×`;
}

export function clamp01(x: number): number {
  return Math.min(1, Math.max(0, x));
}

function joinList(items: string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

// ---------------------------------------------------------------- headline

export function holdoutSummary(sc: Scorecard): { nSites: number; states: string[] } {
  const held = eligibleSites(sc).filter((s) => s.split === "holdout");
  const states = sc.holdout_states?.length ? sc.holdout_states : [...new Set(held.map((s) => s.state))].sort();
  return { nSites: sc.n_holdout_sites ?? held.length, states };
}

export function eligibleSites(sc: Scorecard) {
  return (sc.sites ?? []).filter((s) => s.status === undefined || s.status === "done");
}

export interface Headline {
  /** gain: at least one class improved with a CI above zero; null: none did; pending: no fusion rows yet. */
  kind: "gain" | "null" | "pending";
  text: string;
  detail: string | null;
}

export function fusionHeadline(sc: Scorecard): Headline {
  const rows = (sc.fusion ?? []).filter((r) => isNum(r.delta) && isNum(r.ci_low) && isNum(r.ci_high));
  if (rows.length === 0) {
    return { kind: "pending", text: "Held-out fusion results pending.", detail: null };
  }
  const gains = rows.filter((r) => r.ci_low > 0).sort((a, b) => b.delta - a.delta);
  const losses = rows.filter((r) => r.ci_high < 0).sort((a, b) => a.delta - b.delta);
  const named = (rs: FusionRow[]) => joinList(rs.map((r) => `${classLabel(r.class)} (${signed(r.delta)})`));
  const lossNote = losses.length ? `Lower AUPRC for ${named(losses)}.` : null;

  if (gains.length === 0) {
    return {
      kind: "null",
      text: "No demonstrated fusion gain on held-out states.",
      detail: lossNote ?? "All 95% intervals on the AUPRC difference include zero.",
    };
  }
  const [best, ...others] = gains;
  const parts = [others.length ? `Additional gains: ${named(others)}.` : null, lossNote].filter((p): p is string => p !== null);
  return {
    kind: "gain",
    text:
      `${classTitle(best.class)}: ${signed(best.delta)} AUPRC ` +
      `(95% CI ${fmt(best.ci_low)} to ${fmt(best.ci_high)}) versus ${detectorInfo(best.best_single).label}.`,
    detail: parts.length ? parts.join(" ") : null,
  };
}

// ---------------------------------------------------------------- per-class grouping

export interface ClassGroup {
  key: string;
  cls: string;
  landcover: string;
  /** Reference blocks in this class and land cover (largest across detectors). */
  nRef: number;
  rows: ScorecardClassRow[];
}

function classRank(cls: string): number {
  const i = (CHANGE_CLASSES as readonly string[]).indexOf(cls);
  return i === -1 ? CHANGE_CLASSES.length : i;
}

function detectorRank(d: string): number {
  const i = DETECTORS.indexOf(d as Detector);
  return i === -1 ? DETECTORS.length : i;
}

export function groupClasses(rows: ScorecardClassRow[]): ClassGroup[] {
  const groups = new Map<string, ClassGroup>();
  for (const r of rows) {
    const key = `${r.class}|${r.landcover}`;
    const g = groups.get(key) ?? { key, cls: r.class, landcover: r.landcover, nRef: 0, rows: [] };
    g.rows.push(r);
    if (isNum(r.n_ref)) g.nRef = Math.max(g.nRef, r.n_ref);
    groups.set(key, g);
  }
  const out = [...groups.values()];
  for (const g of out) g.rows.sort((a, b) => detectorRank(a.detector) - detectorRank(b.detector));
  return out.sort(
    (a, b) => classRank(a.cls) - classRank(b.cls) || a.cls.localeCompare(b.cls) || a.landcover.localeCompare(b.landcover),
  );
}

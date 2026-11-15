// TypeScript mirror of the shared Result contract (plan "Contract"; Python twin: core/sarstellar/types.py).
// JSON keys are exactly the contract's keys, so JSON from stories, fixtures and the job API maps 1:1.

/** ISO 8601 date ("2026-07-13") or UTC datetime ("2026-07-13T03:09:56Z"). */
export type IsoDate = string;

/** [west, south, east, north] in degrees. */
export type Bbox = [number, number, number, number];

export type LonLat = [number, number];

export type Agreement = "L" | "C" | "both";

export const CHANGE_CLASSES = [
  "forest_loss",
  "burn",
  "flood_open_water",
  "flooded_vegetation",
  "crop_cycle",
  "harvest",
  "low_veg_loss",
  "soil_wetting",
  "construction",
  "landslide",
  "wet_snow",
  "uncertain",
] as const;

export type ChangeClass = (typeof CHANGE_CLASSES)[number];

export type ConfidenceLabel = "High" | "Medium" | "Low";

/** Fixed meaning everywhere: amber = only NISAR, violet = both, cyan = only Sentinel-1. */
export const AGREEMENT_COLORS: Record<Agreement, string> = {
  L: "#f59e0b",
  both: "#a78bfa",
  C: "#22d3ee",
};

/** Permanent NISAR data gap (UTC). */
export const NISAR_GAP = { start: "2026-07-27T22:03:00Z", end: "2026-08-10T00:55:00Z" } as const;

// Minimal GeoJSON geometry types (positions are [lon, lat]).
export interface GeoPolygon {
  type: "Polygon";
  coordinates: LonLat[][];
}

export interface GeoMultiPolygon {
  type: "MultiPolygon";
  coordinates: LonLat[][][];
}

export interface Evidence {
  label: string;
  value: number | string | null;
  /** 95% interval [low, high] in `unit`, or null when not computed. */
  ci: [number, number] | null;
  unit: string;
  note: string;
}

/** One value per date per band; null where that band has no pass on that date. */
export interface Series {
  dates: IsoDate[];
  HH: (number | null)[];
  HV: (number | null)[];
  VV: (number | null)[];
  VH: (number | null)[];
}

export interface ChangeArea {
  id: string;
  geometry: GeoPolygon | GeoMultiPolygon;
  agreement: Agreement;
  class: ChangeClass;
  area_ha: number;
  /** 0..1 */
  confidence: number;
  confidence_label: ConfidenceLabel;
  p_value: number;
  change_date: IsoDate | null;
  evidence: Evidence[];
  plain_text: string;
  series: Series;
}

export interface Overlays {
  change_png: string;
  l_png: string;
  c_png: string;
  before_png: string;
  after_png: string;
  /** Image corners: upper-left, upper-right, lower-right, lower-left. */
  bounds: [LonLat, LonLat, LonLat, LonLat];
}

export interface SviTract {
  geoid: string;
  /** CDC SVI 2022 overall percentile rank, 0..1. */
  rpl_themes: number;
  name: string;
}

export interface Result {
  bbox: Bbox;
  message: string | null;
  /** True for spike-derived stand-ins; never shown as real results. */
  fixture: boolean;
  nisar: { track: number; direction: "A" | "D"; dates: IsoDate[] };
  s1: { track: number; dates: IsoDate[] } | null;
  overlays: Overlays;
  areas: ChangeArea[];
  people: { svi_tracts: SviTract[] };
  exports: { geotiff: string | null; csv: string | null; notebook: string | null };
}

export type JobStatus = "queued" | "running" | "done" | "error";

export interface Job {
  job_id: string;
  status: JobStatus;
  /** 0..1 */
  progress: number;
  message: string;
  result: Result | null;
}

/** Entry of /stories/index.json (written by Task A8). */
export interface StoryIndexEntry {
  id: string;
  title: string;
  place: string;
  /** [first, last] date compared. */
  dates: IsoDate[];
  summary: string;
}

// ---- Scorecard (/scorecard.json, written by Task C2; `model` filled by C3) ----

export type Detector = "L" | "C" | "L30" | "fused_fisher" | "fused_logistic";

export interface ScorecardClassRow {
  class: string;
  landcover: string;
  detector: Detector;
  precision: number;
  recall: number;
  f1: number;
  auprc: number;
  ci_low: number;
  ci_high: number;
  n_ref: number;
  n_flags: number;
}

export interface EqualRecallRow {
  class: string;
  recall: number;
  precision_L: number;
  precision_C: number;
  precision_L30: number;
  ratio_L_over_C: number;
}

export interface FusionRow {
  class: string;
  best_single: Detector;
  fused: Detector;
  metric: "auprc";
  delta: number;
  ci_low: number;
  ci_high: number;
  /** Bootstrap share of resamples with delta > 0. */
  p_gt0: number;
}

export interface ScorecardModel {
  per_class: { class: string; rules_f1: number; model_f1: number; winner: "rules" | "model" | string }[];
  macro_f1_rules: number;
  macro_f1_model: number;
}

export interface ScorecardSite {
  id: string;
  kind: "forest_loss" | "fire" | "flood" | "crops" | "stable";
  bbox: Bbox;
  state: string;
  split: "train" | "holdout" | string;
}

export interface Scorecard {
  generated_at: string;
  n_sites: number;
  operating_point: { q: number; min_db: number };
  stable_fa: Record<Detector, number>;
  classes: ScorecardClassRow[];
  equal_recall: EqualRecallRow[];
  fusion: FusionRow[];
  model: ScorecardModel | null;
  holdout_states: string[];
  sites: ScorecardSite[];
}

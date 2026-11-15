// Test-only scorecard in the exact /scorecard.json shape (plan Task C2). Values are made up for tests;
// the app only ever shows the real file written by the scorecard batch.
import type { Detector, Scorecard, ScorecardClassRow, ScorecardSite } from "../types.ts";

function row(cls: string, landcover: string, detector: Detector, auprc: number, ci: [number, number]): ScorecardClassRow {
  return {
    class: cls,
    landcover,
    detector,
    precision: auprc - 0.1,
    recall: 0.5,
    f1: auprc - 0.05,
    auprc,
    ci_low: ci[0],
    ci_high: ci[1],
    n_ref: 1200,
    n_flags: 900,
  };
}

/** Rough state centers so the sample spreads across the map like real sites (boxes ~10 km a side). */
const CENTERS: Record<string, [number, number]> = {
  WA: [-122.2, 46.7],
  CA: [-120.5, 37.2],
  TX: [-94.2, 30.3],
  OR: [-122.6, 44.2],
  GA: [-83.6, 32.6],
};

function site(id: string, state: string, split: "train" | "holdout", kind: ScorecardSite["kind"] = "forest_loss"): ScorecardSite {
  const [lon, lat] = CENTERS[state];
  const k = Number(id.slice(1)) * 0.3;
  return { id, kind, bbox: [lon + k - 0.06, lat - 0.045, lon + k + 0.06, lat + 0.045], state, split };
}

export function sampleScorecard(overrides: Partial<Scorecard> = {}): Scorecard {
  return {
    generated_at: "2026-11-15T09:30:00Z",
    n_sites: 8,
    operating_point: { q: 0.05, min_db: 2.0 },
    stable_fa: { L: 0.012, C: 0.009, L30: 0.011, fused_fisher: 0.008, fused_logistic: 0.007 },
    classes: [
      row("burn", "shrub", "C", 0.47, [0.36, 0.58]),
      row("burn", "shrub", "L", 0.18, [0.1, 0.27]),
      row("burn", "shrub", "fused_fisher", 0.49, [0.38, 0.6]),
      row("forest_loss", "forest", "fused_logistic", 0.73, [0.65, 0.8]),
      row("forest_loss", "forest", "C", 0.22, [0.15, 0.3]),
      row("forest_loss", "forest", "L", 0.61, [0.52, 0.7]),
      row("forest_loss", "forest", "L30", 0.48, [0.4, 0.57]),
      row("forest_loss", "forest", "fused_fisher", 0.66, [0.58, 0.74]),
    ],
    equal_recall: [
      { class: "forest_loss", recall: 0.5, precision_L: 0.4, precision_C: 0.13, precision_L30: 0.31, ratio_L_over_C: 3.08 },
      { class: "burn", recall: 0.4, precision_L: 0.09, precision_C: 0.38, precision_L30: 0.08, ratio_L_over_C: 0.24 },
    ],
    fusion: [
      { class: "burn", best_single: "C", fused: "fused_fisher", metric: "auprc", delta: 0.02, ci_low: -0.05, ci_high: 0.09, p_gt0: 0.71 },
      { class: "forest_loss", best_single: "L", fused: "fused_logistic", metric: "auprc", delta: 0.12, ci_low: 0.04, ci_high: 0.2, p_gt0: 0.998 },
    ],
    model: null,
    holdout_states: ["OR", "GA"],
    sites: [
      site("s1", "WA", "train"),
      site("s2", "WA", "train", "fire"),
      site("s3", "CA", "train", "crops"),
      site("s4", "TX", "train", "flood"),
      site("s5", "OR", "holdout"),
      site("s6", "OR", "holdout", "fire"),
      site("s7", "GA", "holdout", "flood"),
      site("s8", "GA", "holdout", "stable"),
    ],
    ...overrides,
  };
}

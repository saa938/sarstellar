import { describe, expect, it } from "vitest";
import type { FusionRow } from "../types.ts";
import { fusionHeadline, groupClasses, holdoutSummary, ratio, signed } from "./scorecardModel.ts";
import { sampleScorecard } from "./scorecardSample.ts";

const fusionRow = (cls: string, delta: number, lo: number, hi: number): FusionRow => ({
  class: cls,
  best_single: "L",
  fused: "fused_fisher",
  metric: "auprc",
  delta,
  ci_low: lo,
  ci_high: hi,
  p_gt0: 0.9,
});

describe("fusionHeadline", () => {
  it("leads with the largest gain whose interval clears zero", () => {
    const h = fusionHeadline(sampleScorecard());
    expect(h.kind).toBe("gain");
    expect(h.text).toBe(
      "Forest loss: +0.12 AUPRC (95% CI 0.04 to 0.20) versus NISAR (L-band).",
    );
  });

  it("names other gains and any losses in the detail line", () => {
    const sc = sampleScorecard({
      fusion: [fusionRow("burn", 0.05, 0.01, 0.09), fusionRow("forest_loss", 0.12, 0.04, 0.2), fusionRow("crop_cycle", -0.08, -0.12, -0.03)],
    });
    const h = fusionHeadline(sc);
    expect(h.text).toContain("Forest loss: +0.12 AUPRC");
    expect(h.detail).toContain("burn (+0.05)");
    expect(h.detail).toContain("Lower AUPRC for cultivated land (proxy) (−0.08)");
  });

  it("reports the honest null when every interval includes zero", () => {
    const h = fusionHeadline(sampleScorecard({ fusion: [fusionRow("forest_loss", 0.03, -0.01, 0.07)] }));
    expect(h.kind).toBe("null");
    expect(h.text).toBe(
      "No detectable fusion gain on held-out states.",
    );
    expect(h.detail).toContain("include zero");
  });

  it("says the test is pending when there are no fusion rows", () => {
    expect(fusionHeadline(sampleScorecard({ fusion: [] })).kind).toBe("pending");
  });
});

describe("helpers", () => {
  it("counts held-out sites and falls back to their states", () => {
    expect(holdoutSummary(sampleScorecard())).toEqual({ nSites: 4, states: ["OR", "GA"] });
    expect(holdoutSummary(sampleScorecard({ holdout_states: [] })).states).toEqual(["GA", "OR"]);
  });

  it("excludes failed and unavailable sites from held-out headline counts", () => {
    const sc = sampleScorecard();
    sc.sites[4].status = "error";
    sc.sites[5].status = "excluded";
    expect(holdoutSummary(sc).nSites).toBe(2);
    expect(holdoutSummary({ ...sc, n_holdout_sites: 2 }).nSites).toBe(2);
  });

  it("orders and labels Bonferroni fusion after Fisher fusion", () => {
    const sc = sampleScorecard();
    const prototype = sc.classes.find((r) => r.class === "forest_loss")!;
    const groups = groupClasses([...sc.classes, { ...prototype, detector: "fused_bonferroni" }]);
    expect(groups[0].rows.map((r) => r.detector)).toEqual(
      ["L", "L30", "C", "fused_fisher", "fused_bonferroni", "fused_logistic"],
    );
  });

  it("groups class rows in contract order with detectors in a fixed order", () => {
    const groups = groupClasses(sampleScorecard().classes);
    expect(groups.map((g) => g.cls)).toEqual(["forest_loss", "burn"]);
    expect(groups[0].rows.map((r) => r.detector)).toEqual(["L", "L30", "C", "fused_fisher", "fused_logistic"]);
  });

  it("formats signed deltas and ratios", () => {
    expect(signed(0.12)).toBe("+0.12");
    expect(signed(-0.08)).toBe("−0.08");
    expect(ratio(3.08)).toBe("3.1×");
    expect(ratio(0.24)).toBe("0.24×");
    expect(ratio(Number.NaN)).toBe("—");
  });
});

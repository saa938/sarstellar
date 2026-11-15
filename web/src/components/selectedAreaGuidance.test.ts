import { describe, expect, it } from "vitest";
import { CHANGE_CLASSES, type ChangeClass, type Evidence } from "../types.ts";
import { displayRuleText, guidanceFor, supportingEvidence } from "./selectedAreaGuidance.ts";

describe("selected-area hypotheses", () => {
  it("qualifies causal classes and leaves uncertain classes unresolved", () => {
    for (const cls of CHANGE_CLASSES) {
      const guidance = guidanceFor(cls);
      if (cls === "uncertain") expect(guidance.hypothesis).toBe("Cause unresolved");
      else expect(guidance.hypothesis).toMatch(/^Possible /);
      expect(guidance.checks).toHaveLength(2);
      expect(guidance.caveat.length).toBeGreaterThan(0);
    }
    expect(guidanceFor("unsupported" as ChangeClass).hypothesis).toBe("Cause unresolved");
  });

  it("distinguishes independent checks for fire, flood, and crop hypotheses", () => {
    expect(guidanceFor("burn").checks.join(" ")).toContain("optical burn scars");
    expect(guidanceFor("flood_open_water").checks.join(" ")).toContain("river gauges");
    expect(guidanceFor("crop_cycle").caveat).toContain("does not establish growth or harvest timing");
  });
});

it("qualifies legacy cause wording for presentation without modifying evidence", () => {
  const original = Object.freeze({ label: "Rule fired", value: "HV fell 3 dB or more (canopy removed)" });
  expect(displayRuleText(original.value)).toBe("HV fell 3 dB or more (consistent with canopy loss)");
  expect(original.value).toBe("HV fell 3 dB or more (canopy removed)");
  expect(displayRuleText("HH rose: double bounce off standing water")).toBe("HH rose: possible double-bounce response");
  expect(displayRuleText("HV changed −3.5 dB")).toBe("HV changed −3.5 dB");
});

it("uses actual rule and signal evidence rather than a p-value as causal support", () => {
  const p: Evidence = { label: "p-value", value: 1e-10, ci: null, unit: "", note: "" };
  const signal: Evidence = { label: "HV change", value: -3.6, ci: [-3.9, -3.3], unit: "dB", note: "NISAR" };
  const rule: Evidence = { label: "Rule fired", value: "HV decrease over forest", ci: null, unit: "", note: "Heuristic" };
  const confidence: Evidence = { label: "Confidence", value: 0.99, ci: null, unit: "", note: "" };
  const original = [p, signal, rule, confidence];
  expect(supportingEvidence(original)).toEqual([rule, signal]);
  expect(signal.ci).toEqual([-3.9, -3.3]);
  expect(original).toEqual([p, signal, rule, confidence]);
  expect(supportingEvidence([p, confidence])).toEqual([]);
});

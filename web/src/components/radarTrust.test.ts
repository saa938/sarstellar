import { describe, expect, it } from "vitest";
import type { EqualRecallRow } from "../types.ts";
import { radarTrust } from "./radarTrust.ts";

const row = (cls: string, l: number, c: number): EqualRecallRow => ({
  class: cls, recall: 0.5, precision_L: l, precision_C: c, precision_L30: l, ratio_L_over_C: l / c,
});
const ROWS = [
  row("forest_loss", 0.311, 0.04),
  row("burn", 0.326, 0.278),
  row("flood_open_water", 0.007, 0.094),
  row("crop_cycle", 0.414, 0.253),
];

describe("radarTrust", () => {
  it("backs a NISAR-only forest-loss detection", () => {
    const v = radarTrust({ class: "forest_loss", agreement: "L" }, ROWS);
    expect(v.tone).toBe("consistent");
    expect(v.headline).toContain("NISAR is the specialist for forest loss");
    expect(v.detail).toContain("31.1%");
    expect(v.detail).toContain("4.0%");
  });

  it("flags a NISAR-only flood because Sentinel-1 was stronger", () => {
    const v = radarTrust({ class: "flood_open_water", agreement: "L" }, ROWS);
    expect(v.tone).toBe("caution");
    expect(v.headline).toContain("Sentinel-1 is the stronger radar");
  });

  it("calls close results a tie", () => {
    const v = radarTrust({ class: "burn", agreement: "C" }, ROWS);
    expect(v.tone).toBe("caution");
    expect(v.headline).toContain("neither radar was clearly better");
  });

  it("names the specialist when both radars agree", () => {
    const v = radarTrust({ class: "harvest", agreement: "both" }, ROWS);
    expect(v.tone).toBe("agree");
    expect(v.headline).toContain("NISAR is the specialist for cultivated-land change");
  });

  it("says so when the cause was never tested or the scorecard is missing", () => {
    expect(radarTrust({ class: "landslide", agreement: "L" }, ROWS).tone).toBe("none");
    expect(radarTrust({ class: "forest_loss", agreement: "L" }, undefined).tone).toBe("none");
  });
});

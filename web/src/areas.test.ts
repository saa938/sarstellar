import { describe, expect, it } from "vitest";
import { AREA_LIST_LIMIT, areasToGeoJSON, formatDateRange, hectareSums, largestAreas, visibleFilter } from "./areas.ts";
import { area } from "./test/sample.ts";
import type { Agreement } from "./types.ts";

describe("hectareSums", () => {
  it("hectare sums match areas", () => {
    const areas = [area("a", "L", 12.4), area("b", "L", 3), area("c", "both", 7), area("d", "C", 1.5), area("e", "C", 2)];
    expect(hectareSums(areas)).toEqual({ L: 15.4, both: 7, C: 3.5 });
  });

  it("is zero for an agreement with no areas", () => {
    expect(hectareSums([area("a", "both", 4)])).toEqual({ L: 0, both: 4, C: 0 });
  });
});

describe("largestAreas", () => {
  it("lists only the 25 largest of a big result, largest first", () => {
    const areas = Array.from({ length: 210 }, (_, i) => area(`a${i}`, i % 2 ? "L" : "C", i + 1));
    const top = largestAreas(areas);
    expect(AREA_LIST_LIMIT).toBe(25);
    expect(top).toHaveLength(25);
    expect(top[0].id).toBe("a209");
    expect(top[24].id).toBe("a185");
  });

  it("lists every area when there are 25 or fewer", () => {
    const top = largestAreas([area("small", "L", 1), area("big", "C", 9)]);
    expect(top.map((a) => a.id)).toEqual(["big", "small"]);
  });
});

describe("formatDateRange", () => {
  it("formats a date range in UTC", () => {
    expect(formatDateRange(["2026-07-13", "2026-09-11"])).toBe("Jul 13 – Sep 11, 2026");
    expect(formatDateRange(["2025-12-01", "2026-01-10"])).toBe("Dec 1, 2025 – Jan 10, 2026");
    expect(formatDateRange(["2026-07-13"])).toBe("Jul 13, 2026");
    expect(formatDateRange([])).toBe("");
  });
});

describe("map data", () => {
  it("turns areas into features keyed by id and agreement, largest first", () => {
    const fc = areasToGeoJSON([area("a", "L", 1), area("b", "C", 2)]);
    expect(fc.type).toBe("FeatureCollection");
    expect(fc.features.map((f) => f.properties)).toEqual([
      { id: "b", agreement: "C" },
      { id: "a", agreement: "L" },
    ]);
  });

  it("filter excludes hidden agreements", () => {
    expect(visibleFilter(new Set<Agreement>(["L", "C"]))).toEqual(["!", ["in", ["get", "agreement"], ["literal", ["L", "C"]]]]);
    expect(visibleFilter(new Set())).toEqual(["!", ["in", ["get", "agreement"], ["literal", []]]]);
  });
});

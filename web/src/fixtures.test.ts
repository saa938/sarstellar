// Keeps public/fixtures/ in the exact contract shape (plan "Contract"), so B2-B6 can rely on them.
import { describe, expect, it } from "vitest";
import { isResult } from "./api.ts";
import { CHANGE_CLASSES, type Result } from "./types.ts";

const jsons = import.meta.glob<unknown>("../public/fixtures/*.json", { eager: true, import: "default" });
const pngs = Object.keys(import.meta.glob("../public/fixtures/*/*.png"));
const index = jsons["../public/fixtures/index.json"] as { id: string }[];
const fixtures = Object.entries(jsons).filter(([path]) => !path.endsWith("/index.json"));

const keys = (o: object) => Object.keys(o).sort();
const RESULT_KEYS = ["areas", "bbox", "exports", "fixture", "message", "nisar", "overlays", "people", "s1"];
const AREA_KEYS = ["agreement", "area_ha", "change_date", "class", "confidence", "confidence_label", "evidence", "geometry", "id", "p_value", "plain_text", "series"];
const OVERLAY_KEYS = ["after_png", "before_png", "bounds", "c_png", "change_png", "l_png"];

describe("fixtures", () => {
  it("index lists the three stories, each with a fixture file", () => {
    expect(index.map((e) => e.id)).toEqual(["clearcuts", "kaiser", "edouard"]);
    for (const { id } of index) expect(jsons[`../public/fixtures/${id}.json`]).toBeDefined();
  });

  it("has no confident uncertain areas and at least one Low area", () => {
    const areas = fixtures.flatMap(([, d]) => (d as Result).areas);
    expect(areas.filter((a) => a.class === "uncertain" && a.confidence_label === "High")).toEqual([]);
    expect(areas.some((a) => a.confidence_label === "Low")).toBe(true);
  });

  it.each(fixtures)("%s matches the Result contract", (path, data) => {
    expect(isResult(data)).toBe(true);
    const r = data as Result;
    const id = path.split("/").pop()!.replace(".json", "");
    expect(r.fixture).toBe(true);
    expect(keys(r)).toEqual(RESULT_KEYS);
    expect(keys(r.overlays)).toEqual(OVERLAY_KEYS);
    expect(keys(r.exports)).toEqual(["csv", "geotiff", "notebook"]);
    for (const k of ["change_png", "l_png", "c_png", "before_png", "after_png"] as const) {
      expect(pngs).toContain(`../public/fixtures/${r.overlays[k]}`);
    }
    const [w, s, e, n] = r.bbox;
    for (const [lon, lat] of r.overlays.bounds) {
      expect(lon).toBeGreaterThan(w - 0.1);
      expect(lon).toBeLessThan(e + 0.1);
      expect(lat).toBeGreaterThan(s - 0.1);
      expect(lat).toBeLessThan(n + 0.1);
    }
    expect(new Set(r.areas.map((a) => a.agreement))).toEqual(new Set(["L", "both", "C"]));
    expect(new Set(r.areas.map((a) => a.id)).size).toBe(r.areas.length);
    for (const a of r.areas) {
      expect(keys(a)).toEqual(AREA_KEYS);
      expect(a.id.startsWith(id)).toBe(true);
      expect(CHANGE_CLASSES).toContain(a.class);
      expect(["High", "Medium", "Low"]).toContain(a.confidence_label);
      expect(a.confidence).toBeGreaterThanOrEqual(0);
      expect(a.confidence).toBeLessThanOrEqual(1);
      expect(a.area_ha).toBeGreaterThanOrEqual(3);
      expect(a.p_value).toBeGreaterThan(0);
      for (const ev of a.evidence) expect(keys(ev)).toEqual(["ci", "label", "note", "unit", "value"]);
      for (const b of ["HH", "HV", "VV", "VH"] as const) expect(a.series[b]).toHaveLength(a.series.dates.length);
    }
    for (const a of r.areas) {
      // Label and score agree; unexplained changes are never confident; Edouard's spike verdict was "moderate".
      const [lo, hi] = { High: [0.8, 1], Medium: [0.5, 0.79], Low: [0, 0.49] }[a.confidence_label];
      expect(a.confidence).toBeGreaterThanOrEqual(lo);
      expect(a.confidence).toBeLessThanOrEqual(hi);
      if (a.class === "uncertain") {
        expect(a.confidence_label).toBe("Low");
        expect(a.confidence).toBeLessThanOrEqual(0.4);
      }
      if (id === "edouard") expect(a.confidence_label).not.toBe("High");
    }
    for (const t of r.people.svi_tracts) {
      expect(keys(t)).toEqual(["geoid", "name", "rpl_themes"]);
      expect(t.rpl_themes).toBeGreaterThanOrEqual(0);
      expect(t.rpl_themes).toBeLessThanOrEqual(1);
    }
  });
});

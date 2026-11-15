// Small hand-built Results for component tests (real fixtures are covered by fixtures.test.ts).
import type { Agreement, ChangeArea, Result } from "../types.ts";

export function area(id: string, agreement: Agreement, area_ha: number): ChangeArea {
  return {
    id,
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [-119.1, 48.2],
          [-119.0, 48.2],
          [-119.0, 48.3],
          [-119.1, 48.2],
        ],
      ],
    },
    agreement,
    class: "burn",
    area_ha,
    confidence: 0.9,
    confidence_label: "High",
    p_value: 0.001,
    change_date: null,
    evidence: [],
    plain_text: `Area ${id} changed.`,
    series: { dates: [], HH: [], HV: [], VV: [], VH: [] },
  };
}

export function sampleResult(overrides: Partial<Result> = {}): Result {
  return {
    bbox: [-119.37, 48.05, -118.72, 48.36],
    message: null,
    fixture: false,
    nisar: { track: 71, direction: "D", dates: ["2026-07-13", "2026-07-25", "2026-09-11"] },
    s1: { track: 166, dates: ["2026-07-11", "2026-09-09"] },
    overlays: {
      change_png: "http://localhost/kaiser/change.png",
      l_png: "http://localhost/kaiser/l.png",
      c_png: "http://localhost/kaiser/c.png",
      before_png: "http://localhost/kaiser/before.png",
      after_png: "http://localhost/kaiser/after.png",
      bounds: [
        [-119.4, 48.4],
        [-118.7, 48.4],
        [-118.7, 48.0],
        [-119.4, 48.0],
      ],
    },
    areas: [area("a1", "L", 6000.4), area("a2", "L", 240), area("a3", "both", 410), area("a4", "C", 380)],
    people: { svi_tracts: [] },
    exports: { geotiff: null, csv: null, notebook: null },
    ...overrides,
  };
}

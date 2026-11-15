import type { Map as MapLibreMap } from "maplibre-gl";
import { describe, expect, it } from "vitest";
import type { Agreement, ChangeArea } from "../types.ts";
import { formatHa, formatPass, loadCompare, overlayUrl, radarStyle, sensorTotals, syncMaps } from "./comparisonmaphelpers.ts";
import { FakeMap } from "./comparisonTestMaps.ts";

const asMap = (m: FakeMap) => m as unknown as MapLibreMap;

function area(agreement: Agreement, area_ha: number): ChangeArea {
  return { agreement, area_ha } as ChangeArea;
}

describe("sensorTotals", () => {
  it("sums whole-patch categories and retains legacy combined sums without claiming flagged-block area", () => {
    const t = sensorTotals([area("L", 100), area("both", 10), area("C", 5), area("L", 1.5)]);
    expect(t).toEqual({ nisar: 111.5, s1: 15, onlyNisar: 101.5, onlyS1: 5, both: 10 });
  });

  it("is zero without areas", () => {
    expect(sensorTotals([])).toEqual({ nisar: 0, s1: 0, onlyNisar: 0, onlyS1: 0, both: 0 });
  });
});

describe("formatting", () => {
  it("rounds hectares with thousands separators", () => {
    expect(formatHa(6650.4)).toBe("6,650 ha");
  });

  it("formats date-only and datetime passes in UTC", () => {
    expect(formatPass("2026-07-13")).toBe("Jul 13, 2026");
    expect(formatPass("2026-09-23T23:59:00Z")).toBe("Sep 23, 2026");
    expect(formatPass(undefined)).toBeNull();
    expect(formatPass("not a date")).toBeNull();
  });
});

describe("radarStyle", () => {
  it("puts the radar image at the overlay corners over a muted basemap", () => {
    const corners: [number, number][] = [[0, 1], [1, 1], [1, 0], [0, 0]];
    const style = radarStyle({ url: "http://x/l.png", corners: corners as never, resampling: "nearest" });
    expect(style.sources.radar).toMatchObject({ type: "image", url: "http://x/l.png", coordinates: corners });
    expect(style.layers.map((l) => l.id)).toEqual(["background", "satellite-imagery", "radar", "areas", "selected-area-halo", "selected-area-outline"]);
  });
});

describe("syncMaps", () => {
  it("mirrors the camera both ways without looping, and detaches", () => {
    const a = new FakeMap({});
    const b = new FakeMap({});
    const stop = syncMaps(asMap(a), asMap(b));
    a.jumpTo({ center: { lng: 5, lat: 6 }, zoom: 9, bearing: 0, pitch: 0 });
    expect(b.center).toEqual({ lng: 5, lat: 6 });
    expect(b.zoom).toBe(9);
    b.jumpTo({ center: { lng: 7, lat: 8 }, zoom: 10 });
    expect(a.center).toEqual({ lng: 7, lat: 8 });
    stop();
    expect(a.listenerCount("move") + b.listenerCount("move")).toBe(0);
  });
});

describe("loadCompare", () => {
  it("uses the normal module entry without mutating the browser global", async () => {
    const Compare = await loadCompare();
    expect(typeof Compare).toBe("function");
    expect(typeof Compare.prototype.setSlider).toBe("function");
    expect("maplibregl" in window).toBe(false);
    expect(await loadCompare()).toBe(Compare);
  });
});

it("normalizes relative image URLs and rejects missing or executable URLs", () => {
  expect(overlayUrl("/stories/kaiser/l.png")).toContain("/stories/kaiser/l.png");
  expect(() => overlayUrl("")).toThrow("missing");
  expect(() => overlayUrl("javascript:alert(1)")).toThrow("unavailable");
});

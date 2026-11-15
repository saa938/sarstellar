import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Agreement, ChangeArea, Result } from "../types.ts";
import { loadCompare } from "./comparisonmaphelpers.ts";
import { FakeCompare, FakeMap, resetFakes } from "./comparisonTestMaps.ts";
import LvsCView from "./LvsCView.tsx";
import SwipeView from "./SwipeView.tsx";

vi.mock("maplibre-gl", async () => {
  const t = await import("./comparisonTestMaps.ts");
  return { Map: t.FakeMap, NavigationControl: t.FakeNavigationControl, setWorkerUrl: vi.fn() };
});
vi.mock("./comparisonmaphelpers.ts", async (importOriginal) => {
  const t = await import("./comparisonTestMaps.ts");
  return { ...(await importOriginal<typeof import("./comparisonmaphelpers.ts")>()),
    loadCompare: vi.fn(async () => t.FakeCompare) };
});

class FakeResizeObserver {
  static instances: FakeResizeObserver[] = [];
  observe = vi.fn();
  disconnect = vi.fn();
  constructor(readonly notify: () => void) { FakeResizeObserver.instances.push(this); }
}

function area(id: string, agreement: Agreement, area_ha: number): ChangeArea {
  return { id, agreement, area_ha, class: "burn", confidence: 0.9, confidence_label: "High",
    p_value: 0.001, change_date: null, evidence: [], plain_text: "",
    geometry: { type: "Polygon", coordinates: [[[-119.1, 48.1], [-119, 48.1], [-119, 48.2], [-119.1, 48.1]]] },
    series: { dates: [], HH: [], HV: [], VV: [], VH: [] } };
}

function result(over: Partial<Result> = {}): Result {
  return {
    bbox: [-119.1, 48.1, -119, 48.2], message: null, fixture: false,
    nisar: { track: 172, direction: "D", dates: ["2026-07-13", "2026-07-25", "2026-09-23T14:02:11Z"] },
    s1: { track: 13, dates: ["2026-07-14", "2026-09-24"] },
    overlays: { change_png: "http://x/change.png", l_png: "http://x/l.png", c_png: "http://x/c.png",
      before_png: "http://x/before.png", after_png: "http://x/after.png",
      bounds: [[-119.1, 48.2], [-119, 48.2], [-119, 48.1], [-119.1, 48.1]] },
    areas: [area("a1", "L", 6240.4), area("a2", "both", 410), area("a3", "C", 380)],
    people: { svi_tracts: [] }, exports: { geotiff: null, csv: null, notebook: null }, ...over,
  };
}

beforeEach(() => {
  resetFakes();
  FakeResizeObserver.instances = [];
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  vi.mocked(loadCompare).mockImplementation(async () => FakeCompare as never);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const flush = () => act(async () => {});

describe("comparison mode transitions", () => {
  it("mounts the right imagery and releases the old comparison on a mode change", async () => {
    const view = render(<SwipeView result={result()} />);
    await flush();
    const [before, after] = FakeMap.instances;
    expect([before.radarUrl, after.radarUrl]).toEqual(["http://x/before.png", "http://x/after.png"]);
    expect(FakeCompare.instances).toHaveLength(1);
    view.rerender(<LvsCView result={result()} />);
    expect(screen.queryByRole("region", { name: /before and after/i })).toBeNull();
    expect(screen.getByRole("region", { name: /L-band vs C-band/i })).toBeTruthy();
    expect(FakeCompare.instances[0].removed).toBe(true);
    expect(before.removed && after.removed).toBe(true);
    expect(FakeMap.instances.slice(2).map((m) => m.radarUrl)).toEqual(["http://x/l.png", "http://x/c.png"]);
    view.unmount();
    expect(FakeMap.instances.every((m) => m.removed)).toBe(true);
    expect(FakeResizeObserver.instances.every((o) => o.disconnect.mock.calls.length === 1)).toBe(true);
  });
});

describe("SwipeView", () => {
  it("uses both dated NISAR overlays and a keyboard slider", async () => {
    render(<SwipeView result={result()} />);
    await flush();
    expect(screen.getByText("Before: NISAR Jul 13, 2026")).toBeTruthy();
    expect(screen.getByText("After: NISAR Sep 23, 2026")).toBeTruthy();
    const region = screen.getByRole("region", { name: /before and after/i });
    Object.defineProperty(region, "clientWidth", { value: 800, configurable: true });
    fireEvent.change(screen.getByRole("slider", { name: /divider/i }), { target: { value: "25" } });
    expect(FakeCompare.instances[0].slider).toBe(200);
    expect(screen.getByRole("slider").getAttribute("aria-valuetext")).toBe("25% before, 75% after");
    act(() => FakeCompare.instances[0].slide(600));
    expect((screen.getByRole("slider") as HTMLInputElement).value).toBe("75");
  });

  it("keeps divider percentage when a parent panel resizes", async () => {
    render(<SwipeView result={result()} />);
    await flush();
    const region = screen.getByRole("region", { name: /before and after/i });
    Object.defineProperty(region, "clientWidth", { value: 800, configurable: true });
    fireEvent.change(screen.getByRole("slider"), { target: { value: "25" } });
    Object.defineProperty(region, "clientWidth", { value: 400 });
    act(() => FakeResizeObserver.instances[0].notify());
    expect(FakeMap.instances.every((m) => m.resizes === 1)).toBe(true);
    expect(FakeCompare.instances[0].slider).toBe(100);
  });

  it("never creates a late control after unmount", async () => {
    let resolve!: (value: typeof FakeCompare) => void;
    vi.mocked(loadCompare).mockImplementationOnce(() => new Promise((done) => { resolve = done as never; }));
    const view = render(<SwipeView result={result()} />);
    view.unmount();
    await act(async () => resolve(FakeCompare));
    expect(FakeCompare.instances).toHaveLength(0);
    expect(FakeMap.instances.every((m) => m.removed)).toBe(true);
  });

  it("reports unavailable imagery without leaving partially mounted maps", async () => {
    const r = result();
    render(<SwipeView result={{ ...r, overlays: { ...r.overlays, after_png: "" } }} />);
    await flush();
    expect(screen.getByRole("alert").textContent).toContain("could not be displayed");
    expect(FakeMap.instances.every((m) => m.removed)).toBe(true);
  });
});

describe("LvsCView", () => {
  it("includes both-sensor areas in each total and preserves delta imagery", () => {
    render(<LvsCView result={result()} />);
    expect(screen.getByRole("group", { name: /NISAR/ }).textContent).toContain("6,650 ha");
    expect(screen.getByRole("group", { name: /Sentinel-1/ }).textContent).toContain("790 ha");
    const [l, c] = FakeMap.instances;
    expect([l.radarUrl, c.radarUrl]).toEqual(["http://x/l.png", "http://x/c.png"]);
    expect(l.outlined.sort()).toEqual(["L", "both"]);
    expect(c.outlined.sort()).toEqual(["C", "both"]);
    expect(screen.getByText("Lower backscatter")).toBeTruthy();
    expect(screen.getByText("Higher backscatter")).toBeTruthy();
    expect(l.options.bounds).toEqual([[-119.1, 48.1], [-119, 48.2]]);
  });

  it("shows actual pass counts and warns about different comparison windows", () => {
    render(<LvsCView result={result()} />);
    expect(screen.getByText(/3 passes · Jul 13, 2026/)).toBeTruthy();
    expect(screen.getByText(/2 passes · Jul 14, 2026/)).toBeTruthy();
    expect(screen.getByText(/Pass dates or counts differ/)).toBeTruthy();
  });

  it("synchronizes cameras both ways without repeated move events and detaches on unmount", () => {
    const view = render(<LvsCView result={result()} />);
    const [l, c] = FakeMap.instances;
    l.jumpTo({ center: { lng: -119.05, lat: 48.15 }, zoom: 12 });
    expect(c.center).toEqual(l.center);
    c.jumpTo({ center: { lng: -119.01, lat: 48.11 }, zoom: 13 });
    expect(l.zoom).toBe(13);
    view.unmount();
    expect(l.listenerCount("move") + c.listenerCount("move")).toBe(0);
  });

  it("does not construct a C map or display a false zero when no S1 pair exists", () => {
    render(<LvsCView result={result({ s1: null })} />);
    expect(FakeMap.instances).toHaveLength(1);
    expect(FakeMap.instances[0].radarUrl).toBe("http://x/l.png");
    expect(screen.getByRole("status").textContent).toContain("No Sentinel-1 pair");
    const missing = screen.getByRole("group", { name: /Sentinel-1/ });
    expect(missing.textContent).toContain("unavailable");
    expect(missing.textContent).not.toContain("ha changed");
  });
});

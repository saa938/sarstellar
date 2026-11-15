import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import fixture from "../../public/fixtures/kaiser.json";
import type { Result } from "../types.ts";
import MapView from "./MapView.tsx";
import { agreementFilter, createBasemapStyle, selectionFilter } from "./mapModel.ts";

type Handler = (event: unknown) => void;
type Source = { spec: Record<string, unknown>; setData: (data: unknown) => void; updateImage: (image: unknown) => void };
interface TestMap {
  options: unknown;
  sources: Map<string, Source>;
  layers: Map<string, Record<string, unknown>>;
  handlers: Map<string, Set<Handler>>;
  fire: (event: string, payload?: unknown, layer?: string) => void;
  fitBounds: ReturnType<typeof vi.fn>;
  resize: ReturnType<typeof vi.fn>;
  remove: ReturnType<typeof vi.fn>;
  canvas: HTMLCanvasElement;
}
const state = vi.hoisted(() => ({ maps: [] as TestMap[], fail: false }));

vi.mock("maplibre-gl", () => {
  class FakeMap {
    options: unknown;
    sources = new globalThis.Map<string, Source>();
    layers = new globalThis.Map<string, Record<string, unknown>>();
    handlers = new globalThis.Map<string, Set<Handler>>();
    canvas = document.createElement("canvas");
    fitBounds = vi.fn();
    resize = vi.fn();
    remove = vi.fn();
    constructor(options: unknown) {
      if (state.fail) throw new Error("No WebGL");
      this.options = options;
      state.maps.push(this);
    }
    addControl() {}
    on(event: string, layerOrHandler: string | Handler, callback?: Handler) {
      const key = `${event}:${typeof layerOrHandler === "string" ? layerOrHandler : ""}`;
      const handlers = this.handlers.get(key) ?? new Set<Handler>();
      handlers.add(typeof layerOrHandler === "string" ? callback! : layerOrHandler);
      this.handlers.set(key, handlers);
    }
    off(event: string, layerOrHandler: string | Handler, callback?: Handler) {
      const key = `${event}:${typeof layerOrHandler === "string" ? layerOrHandler : ""}`;
      this.handlers.get(key)?.delete(typeof layerOrHandler === "string" ? callback! : layerOrHandler);
    }
    fire(event: string, payload: unknown = {}, layer = "") {
      this.handlers.get(`${event}:${layer}`)?.forEach((handler) => handler(payload));
    }
    addSource(id: string, spec: Record<string, unknown>) {
      if (this.sources.has(id)) throw new Error(`Duplicate source ${id}`);
      const source = {
        spec,
        setData: (data: unknown) => { source.spec.data = data; },
        updateImage: (image: unknown) => { Object.assign(source.spec, image); },
      };
      this.sources.set(id, source);
    }
    getSource(id: string) { return this.sources.get(id); }
    addLayer(layer: Record<string, unknown>, before?: string) {
      if (this.layers.has(layer.id as string)) throw new Error("Duplicate layer");
      this.layers.set(layer.id as string, { ...layer, before });
    }
    getLayer(id: string) { return this.layers.get(id); }
    setFilter(id: string, filter: unknown) { this.layers.get(id)!.filter = filter; }
    setLayoutProperty(id: string, key: string, value: unknown) {
      const layer = this.layers.get(id)!;
      layer.layout = { ...(layer.layout as object), [key]: value };
    }
    getCanvas() { return this.canvas; }
  }
  return { Map: FakeMap, NavigationControl: class {}, setWorkerUrl: vi.fn() };
});

const ALL = { L: true, both: true, C: true };
const result = (): Result => structuredClone(fixture) as Result;
const props = () => ({ result: result(), visible: ALL, selectedAreaId: null, onSelectArea: vi.fn() });
const current = () => state.maps.at(-1)!;
const load = () => act(() => current().fire("load"));

beforeEach(() => {
  state.maps.length = 0;
  state.fail = false;
});
afterEach(cleanup);

describe("MapView", () => {
  it("loads the latest result, its image bounds and feature identities after the map is ready", () => {
    const initial = props();
    const onMapReady = vi.fn();
    const { rerender } = render(<MapView {...initial} onMapReady={onMapReady} />);
    const next = result();
    next.overlays.change_png = "/updated.png";
    rerender(<MapView {...initial} result={next} onMapReady={onMapReady} />);
    expect(current().sources.size).toBe(0);
    load();
    const map = current();
    expect(map.sources.get("sarstellar-agreement-image")!.spec).toMatchObject({
      url: "/updated.png", coordinates: next.overlays.bounds,
    });
    expect(map.sources.get("sarstellar-areas")!.spec.data).toMatchObject({
      features: next.areas.map((area) => ({ id: area.id, properties: { id: area.id }, geometry: area.geometry })),
    });
    expect(map.layers.get("sarstellar-agreement")!.before).toBe("sarstellar-area-fill");
    expect(map.fitBounds).toHaveBeenCalledWith(
      [[next.bbox[0], next.bbox[1]], [next.bbox[2], next.bbox[3]]], expect.any(Object),
    );
    expect(onMapReady).toHaveBeenCalledWith(map);
    expect(screen.queryByText("Loading satellite map…")).toBeNull();
  });

  it("filters every category, hides the baked image and keeps hidden selections outlined off", () => {
    const initial = props();
    const { rerender } = render(<MapView {...initial} />);
    load();
    const visible = { L: false, both: true, C: true };
    const selectedAreaId = initial.result.areas[0].id;
    rerender(<MapView {...initial} visible={visible} selectedAreaId={selectedAreaId} />);
    expect(current().layers.get("sarstellar-area-fill")!.filter).toEqual(agreementFilter(visible));
    expect(current().layers.get("sarstellar-area-outline")!.filter).toEqual(selectionFilter(visible, selectedAreaId));
    expect(current().layers.get("sarstellar-agreement")!.layout).toEqual({ visibility: "none" });
    expect(current().fitBounds).toHaveBeenCalledTimes(1);
    expect(agreementFilter({ L: false, both: false, C: false })).toEqual(["in", ["get", "agreement"], ["literal", []]]);
    rerender(<MapView {...initial} />);
    expect(current().layers.get("sarstellar-agreement")!.layout).toEqual({ visibility: "visible" });
  });

  it("uses the newest click callback without replacing maps or duplicating handlers", () => {
    const initial = props();
    const { rerender } = render(<MapView {...initial} />);
    load();
    const nextCallback = vi.fn();
    rerender(<MapView {...initial} onSelectArea={nextCallback} />);
    act(() => current().fire("click", { features: [{ properties: { id: "area-7" } }] }, "sarstellar-area-fill"));
    expect(nextCallback).toHaveBeenCalledExactlyOnceWith("area-7");
    expect(initial.onSelectArea).not.toHaveBeenCalled();
    expect(state.maps).toHaveLength(1);
    expect(current().handlers.get("click:sarstellar-area-fill")!.size).toBe(1);
  });

  it("updates the same image source for a new result and clears it when results disappear", () => {
    const initial = props();
    const { rerender } = render(<MapView {...initial} />);
    load();
    const source = current().sources.get("sarstellar-agreement-image");
    const next = result();
    next.overlays.change_png = "/next.png";
    rerender(<MapView {...initial} result={next} />);
    expect(current().sources.get("sarstellar-agreement-image")).toBe(source);
    expect(source!.spec.url).toBe("/next.png");
    expect(current().fitBounds).toHaveBeenCalledTimes(2);
    rerender(<MapView {...initial} result={null} />);
    expect(current().sources.get("sarstellar-areas")!.spec.data).toMatchObject({ features: [] });
    expect(current().layers.get("sarstellar-agreement")!.layout).toEqual({ visibility: "none" });
  });

  it("resizes and releases maps, callbacks and event handlers in StrictMode", () => {
    const onMapReady = vi.fn();
    const disconnect = vi.fn();
    const observe = vi.fn();
    let resize: ResizeObserverCallback | null = null;
    vi.stubGlobal("ResizeObserver", class {
      constructor(callback: ResizeObserverCallback) { resize = callback; }
      observe = observe;
      disconnect = disconnect;
    });
    const { unmount } = render(<StrictMode><MapView {...props()} onMapReady={onMapReady} /></StrictMode>);
    expect(state.maps).toHaveLength(2);
    expect(state.maps[0].remove).toHaveBeenCalledOnce();
    load();
    const map = current();
    act(() => resize!([], {} as ResizeObserver));
    expect(map.resize).toHaveBeenCalledOnce();
    expect(observe).toHaveBeenCalledTimes(2);
    unmount();
    expect(map.remove).toHaveBeenCalledOnce();
    expect(onMapReady).toHaveBeenLastCalledWith(null);
    expect(disconnect).toHaveBeenCalledTimes(2);
    expect([...map.handlers.values()].every((handlers) => handlers.size === 0)).toBe(true);
    act(() => map.fire("load")); // A late event from a disposed map does not recreate layers.
    expect(map.layers.size).toBe(3);
  });

  it("shows a readable WebGL fallback and can retry", () => {
    state.fail = true;
    render(<MapView {...props()} />);
    expect(screen.getByRole("status").textContent).toContain("WebGL");
    state.fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry map" }));
    load();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("keeps the findings usable when imagery fails", () => {
    render(<MapView {...props()} />);
    load();
    act(() => current().fire("error", { error: new Error("Tile unavailable") }));
    expect(screen.getByRole("status").textContent).toContain("imagery could not load");
    expect(current().remove).not.toHaveBeenCalled();
  });

  it("shares independent muted basemap styles with provider attribution", () => {
    const first = createBasemapStyle();
    const second = createBasemapStyle();
    expect(first).not.toBe(second);
    expect(first.sources.satellite).toMatchObject({ attribution: expect.stringContaining("Esri"), type: "raster" });
  });
});

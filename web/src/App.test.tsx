import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useEffect } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { Map as MapLibreMap } from "maplibre-gl";
import App from "./App.tsx";
import { loadStory, loadStoryIndex } from "./api.ts";
import { sampleResult } from "./test/sample.ts";
import type { Agreement, Result, Scorecard } from "./types.ts";

const state = vi.hoisted(() => ({ map: {} as MapLibreMap, scorecard: null as Scorecard | null }));
vi.mock("./api.ts", async (original) => ({
  ...await original<typeof import("./api.ts")>(), loadStory: vi.fn(), loadStoryIndex: vi.fn(),
}));
vi.mock("./components/MapView.tsx", () => ({
  default: ({ result, visible, onMapReady, onSelectArea }: {
    result: Result | null; visible: Record<Agreement, boolean>;
    onMapReady: (map: MapLibreMap | null) => void; onSelectArea: (id: string) => void;
  }) => {
    useEffect(() => { onMapReady(state.map); return () => onMapReady(null); }, [onMapReady]);
    return <div aria-label="Interactive change map">
      {result?.areas.filter((a) => visible[a.agreement]).map((a) =>
        <button key={a.id} onClick={() => onSelectArea(a.id)}>Map area {a.id}</button>)}
    </div>;
  },
}));
vi.mock("./components/DrawBox.tsx", () => ({
  DrawBox: ({ map, onResult, onStartDrawing }: {
    map: MapLibreMap | null; onResult: (r: Result) => void; onStartDrawing: () => void;
  }) => <button disabled={!map} onClick={() => {
    onStartDrawing(); onResult(sampleResult({ message: "Live result from your box" }));
  }}>Draw analysis area</button>,
}));
vi.mock("./components/SwipeView.tsx", () => ({ default: () => <div>Before and after comparison</div> }));
vi.mock("./components/LvsCView.tsx", () => ({ default: () => <div>NISAR and Sentinel-1 comparison</div> }));
vi.mock("./components/ChangePanel.tsx", () => ({
  ResultExports: () => <section aria-label="Exports">Exports</section>,
  default: ({ area, onClose }: { area: { id: string }; onClose: () => void }) =>
    <section aria-label="Selected change evidence">{area.id}<button onClick={onClose}>Close</button></section>,
}));
vi.mock("./pages/Scorecard.tsx", () => ({
  useScorecard: () => state.scorecard,
  default: () => <h1>National scorecard</h1>,
}));
vi.mock("./pages/About.tsx", () => ({ default: () => <h1>About SARstellar</h1> }));

const stories = [
  { id: "clearcuts", title: "Forest change near Morton", place: "Washington", dates: ["2026-05-21", "2026-09-30"], summary: "Saved pipeline result", fixture: false },
  { id: "kaiser", title: "Kaiser Canyon Fire", place: "Washington", dates: ["2026-07-13", "2026-09-11"], summary: "Saved fire result", fixture: false },
];

beforeEach(() => {
  state.scorecard = null;
  window.localStorage.clear();
  window.location.hash = "#/";
  vi.mocked(loadStoryIndex).mockResolvedValue(stories);
  vi.mocked(loadStory).mockImplementation(async () => sampleResult());
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

async function open() {
  render(<App />);
  await screen.findByRole("heading", { name: stories[0].title });
  await waitFor(() => expect(screen.getByRole("button", { name: "Draw analysis area" }).hasAttribute("disabled")).toBe(false));
}

it("opens the real story and connects legend filtering to the map", async () => {
  await open();
  expect(screen.queryByText("Example data")).toBeNull();
  expect(screen.getByRole("button", { name: "Map area a1" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /^NISAR majority:/ }));
  expect(screen.queryByRole("button", { name: "Map area a1" })).toBeNull();
  expect(screen.getByRole("button", { name: "Map area a3" })).toBeTruthy();
});

it("uses the story site's dark look and links back to its start", async () => {
  await open();
  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(screen.getByRole("link", { name: "SARstellar home" }).getAttribute("href")).toBe("/");
  expect(screen.getByRole("link", { name: "Analyze" }).getAttribute("href")).toBe("/map/");
});

it("switches saved stories and opens change evidence from the map", async () => {
  await open();
  fireEvent.click(screen.getByRole("button", { name: /Kaiser Canyon Fire/ }));
  await screen.findByRole("heading", { name: "Kaiser Canyon Fire" });
  fireEvent.click(screen.getByRole("button", { name: "Map area a1" }));
  const panel = await screen.findByRole("region", { name: "Selected change evidence" });
  expect(panel.textContent).toContain("a1");
  fireEvent.click(within(panel).getByRole("button", { name: "Close" }));
  expect(screen.getByRole("heading", { name: "Kaiser Canyon Fire" })).toBeTruthy();
});

it("renders both comparison modes and brings the change map back when drawing", async () => {
  await open();
  fireEvent.click(screen.getByRole("button", { name: "Before | After" }));
  await screen.findByText("Before and after comparison");
  fireEvent.click(screen.getByRole("button", { name: "L-band vs C-band" }));
  await screen.findByText("NISAR and Sentinel-1 comparison");
  fireEvent.click(screen.getByRole("button", { name: "Draw analysis area" }));
  expect(screen.getByRole("button", { name: "Detected areas" }).getAttribute("aria-pressed")).toBe("true");
  await screen.findByRole("heading", { name: "Analysis area" });
  expect(screen.getByText("Live result from your box")).toBeTruthy();
});

it("keeps the existing map mounted while navigating to methods", async () => {
  await open();
  act(() => { window.location.hash = "#/about"; window.dispatchEvent(new HashChangeEvent("hashchange")); });
  expect(screen.getByRole("heading", { name: "About SARstellar" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Map area a1" })).toBeNull();
  act(() => { window.location.hash = "#/"; window.dispatchEvent(new HashChangeEvent("hashchange")); });
  expect(screen.getByRole("button", { name: "Map area a1" })).toBeTruthy();
});

it("does not let a late story response replace a newer selection", async () => {
  let finishFirst!: (r: Result) => void;
  vi.mocked(loadStory).mockImplementation((id) => id === "clearcuts"
    ? new Promise((resolve) => { finishFirst = resolve; }) : Promise.resolve(sampleResult()));
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /Kaiser Canyon Fire/ }));
  await screen.findByRole("heading", { name: "Kaiser Canyon Fire" });
  await act(async () => { finishFirst(sampleResult()); });
  expect(screen.getByRole("heading", { name: "Kaiser Canyon Fire" })).toBeTruthy();
  expect(screen.queryByRole("heading", { name: stories[0].title })).toBeNull();
});

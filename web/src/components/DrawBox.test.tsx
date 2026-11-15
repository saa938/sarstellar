import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { Map as MaplibreMap } from "maplibre-gl";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, createJob, pollJob } from "../api.ts";
import type { Bbox, Result } from "../types.ts";
import type { BoxDrawer, BoxListener } from "./box.ts";
import { DrawBox } from "./DrawBox.tsx";

vi.mock("../api.ts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api.ts")>();
  return { ...actual, createJob: vi.fn(), pollJob: vi.fn() };
});

const SMALL: Bbox = [-122.3, 46.65, -122.2, 46.7];
const OVERSIZE: Bbox = [-122.3, 46.6, -122.0, 46.8];
const MAP = {} as MaplibreMap;

/** Stand-in for the terra-draw drawer: the test "draws" by calling emit(). */
function fakeDrawer() {
  let listener: BoxListener | null = null;
  const drawer: BoxDrawer = {
    start: vi.fn((l: BoxListener) => {
      listener = l;
    }),
    clear: vi.fn(() => {
      listener = null;
    }),
    destroy: vi.fn(),
  };
  const emit = (bbox: Bbox | null, done: boolean) => act(() => listener?.(bbox, done));
  return { drawer, emit };
}

async function drawBox(bbox: Bbox, onResult = vi.fn()) {
  const { drawer, emit } = fakeDrawer();
  render(<DrawBox map={MAP} onResult={onResult} createDrawer={() => drawer} />);
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Draw a box anywhere" })));
  expect(drawer.start).toHaveBeenCalledTimes(1);
  await emit(bbox, true);
  return { drawer, emit, onResult };
}

function result(overrides: Partial<Result> = {}): Result {
  return {
    bbox: SMALL,
    message: null,
    fixture: false,
    nisar: { track: 71, direction: "D", dates: ["2026-07-13", "2026-09-11"] },
    s1: null,
    overlays: {
      change_png: "c.png",
      l_png: "l.png",
      c_png: "cc.png",
      before_png: "b.png",
      after_png: "a.png",
      bounds: [
        [-122.3, 46.7],
        [-122.2, 46.7],
        [-122.2, 46.65],
        [-122.3, 46.65],
      ],
    },
    areas: [],
    people: { svi_tracts: [] },
    exports: { geotiff: null, csv: null, notebook: null },
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.mocked(createJob).mockReset();
  vi.mocked(pollJob).mockReset();
});

describe("DrawBox", () => {
  it("can cancel a completed rectangle without starting an analysis", async () => {
    await drawBox(SMALL);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Draw a box anywhere" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Analyze this box" })).toBeNull();
    expect(createJob).not.toHaveBeenCalled();
  });

  it("shows a live size readout while drawing", async () => {
    const { drawer, emit } = fakeDrawer();
    render(<DrawBox map={MAP} onResult={vi.fn()} createDrawer={() => drawer} />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Draw a box anywhere" })));
    await emit(SMALL, false);
    expect(screen.getByText("7.6 × 5.6 km · 42 km²")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cancel drawing" })).toBeTruthy();
  });

  it("oversize box blocked before submit", async () => {
    await drawBox(OVERSIZE);
    expect(screen.getByRole("alert").textContent).toBe("Boxes are limited to 20 km a side.");
    const submit = screen.getByRole("button", { name: "Analyze this box" }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    await act(async () => fireEvent.click(submit));
    expect(createJob).not.toHaveBeenCalled();
  });

  it("warns about an oversize box while it is still being drawn", async () => {
    const { drawer, emit } = fakeDrawer();
    render(<DrawBox map={MAP} onResult={vi.fn()} createDrawer={() => drawer} />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Draw a box anywhere" })));
    await emit(OVERSIZE, false);
    expect(screen.getByRole("alert").textContent).toBe("Boxes are limited to 20 km a side.");
  });

  it("server error message shown", async () => {
    const serverMessage = "No calibrated NISAR passes cover this box between 2026-07-01 and 2026-09-30.";
    vi.mocked(createJob).mockResolvedValue({ job_id: "j1" });
    vi.mocked(pollJob).mockImplementation(async (id, onProgress) => {
      onProgress({ job_id: id, status: "running", progress: 0.1, message: "Finding NISAR passes", result: null });
      throw new Error(serverMessage);
    });
    const { onResult } = await drawBox(SMALL);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Analyze this box" })));
    expect((await screen.findByRole("alert")).textContent).toBe(serverMessage);
    expect(onResult).not.toHaveBeenCalled();
  });

  it("shows a 422 detail from the server verbatim", async () => {
    vi.mocked(createJob).mockRejectedValue(new ApiError("Box sides must be at most 20 km (got 20.4 km).", 422));
    await drawBox(SMALL);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Analyze this box" })));
    expect((await screen.findByRole("alert")).textContent).toBe("Box sides must be at most 20 km (got 20.4 km).");
  });

  it("submits the box and dates, then hands the result over and clears the drawing", async () => {
    const done = result({ message: "Most of this box has no valid radar data." });
    vi.mocked(createJob).mockResolvedValue({ job_id: "j2" });
    vi.mocked(pollJob).mockResolvedValue(done);
    const { drawer, emit } = fakeDrawer();
    const onResult = vi.fn();
    render(<DrawBox map={MAP} dates={["2026-07-13", "2026-09-11"]} onResult={onResult} createDrawer={() => drawer} />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Draw a box anywhere" })));
    await emit(SMALL, true);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Analyze this box" })));

    expect(await screen.findByText("Most of this box has no valid radar data.")).toBeTruthy();
    expect(screen.getByText("Analysis complete · no change areas")).toBeTruthy();
    expect(createJob).toHaveBeenCalledWith(SMALL, ["2026-07-13", "2026-09-11"], expect.any(AbortSignal));
    expect(vi.mocked(pollJob).mock.calls[0][3]?.signal).toBeInstanceOf(AbortSignal);
    expect(onResult).toHaveBeenCalledWith(done);
    expect(drawer.clear).toHaveBeenCalled();
  });

  it("disables drawing until the map exists", () => {
    render(<DrawBox map={null} onResult={vi.fn()} createDrawer={() => fakeDrawer().drawer} />);
    expect((screen.getByRole("button", { name: "Draw a box anywhere" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("releases the drawer on unmount", async () => {
    const { drawer } = await drawBox(SMALL);
    cleanup();
    await act(async () => {});
    expect(drawer.destroy).toHaveBeenCalled();
  });
});

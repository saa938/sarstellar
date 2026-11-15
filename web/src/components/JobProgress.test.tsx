import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TIMEOUT_MESSAGE, createJob, pollJob } from "../api.ts";
import type { Bbox, Job } from "../types.ts";
import { JobProgress, STAGES, stageIndex, useLiveJob } from "./JobProgress.tsx";

vi.mock("../api.ts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api.ts")>();
  return { ...actual, createJob: vi.fn(), pollJob: vi.fn() };
});

const SMALL: Bbox = [-122.3, 46.65, -122.2, 46.7];
const OVERSIZE: Bbox = [-122.3, 46.6, -122.0, 46.8];

/** Minimal host for the hook: a start button plus the progress panel. */
function Harness({ bbox = SMALL, onResult = vi.fn() }: { bbox?: Bbox; onResult?: () => void }) {
  const job = useLiveJob(onResult);
  return (
    <>
      <button onClick={() => job.start(bbox)}>go</button>
      <JobProgress state={job.state} onCancel={job.cancel} onDismiss={job.reset} />
    </>
  );
}

afterEach(() => {
  cleanup();
  vi.mocked(createJob).mockReset();
  vi.mocked(pollJob).mockReset();
});

describe("stageIndex", () => {
  it("maps the pipeline's progress fractions to stages", () => {
    // A6 reports 0.1 search, 0.2-0.7 reads, 0.8 test, 0.9 explain.
    expect(STAGES[stageIndex(0)]).toBe("Finding passes");
    expect(STAGES[stageIndex(0.1)]).toBe("Finding passes");
    expect(STAGES[stageIndex(0.2)]).toBe("Reading passes");
    expect(STAGES[stageIndex(0.7)]).toBe("Reading passes");
    expect(STAGES[stageIndex(0.8)]).toBe("Testing every hectare for change");
    expect(STAGES[stageIndex(0.9)]).toBe("Explaining what changed");
    expect(STAGES[stageIndex(1)]).toBe("Explaining what changed");
  });
});

describe("useLiveJob + JobProgress", () => {
  it("shows the current stage, the server's progress message and a progress bar", async () => {
    let report: (job: Job) => void = () => {};
    vi.mocked(createJob).mockResolvedValue({ job_id: "j1" });
    vi.mocked(pollJob).mockImplementation((_id, onProgress) => {
      report = onProgress;
      return new Promise(() => {});
    });
    render(<Harness />);
    await act(async () => fireEvent.click(screen.getByText("go")));
    act(() => report({ job_id: "j1", status: "running", progress: 0.45, message: "Reading 11 passes", result: null }));

    expect(screen.getByText("Reading 11 passes")).toBeTruthy();
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("45");
    const current = screen.getByText("Reading passes");
    expect(current.getAttribute("aria-current")).toBe("step");
  });

  it("shows the timeout message", async () => {
    vi.mocked(createJob).mockResolvedValue({ job_id: "j1" });
    const timeout = new Error(TIMEOUT_MESSAGE);
    timeout.name = "TimeoutError";
    vi.mocked(pollJob).mockRejectedValue(timeout);
    render(<Harness />);
    await act(async () => fireEvent.click(screen.getByText("go")));
    expect((await screen.findByRole("alert")).textContent).toBe(TIMEOUT_MESSAGE);
  });

  it("stays silent when the job is cancelled", async () => {
    vi.mocked(createJob).mockResolvedValue({ job_id: "j1" });
    vi.mocked(pollJob).mockImplementation(
      (_id, _onProgress, _ms, opts) =>
        new Promise((_resolve, reject) => {
          opts?.signal?.addEventListener("abort", () => reject(new DOMException("The operation was aborted.", "AbortError")));
        }),
    );
    render(<Harness />);
    await act(async () => fireEvent.click(screen.getByText("go")));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Cancel" })));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("refuses an oversize box without calling the server", async () => {
    render(<Harness bbox={OVERSIZE} />);
    await act(async () => fireEvent.click(screen.getByText("go")));
    expect(screen.getByRole("alert").textContent).toBe("Boxes are limited to 20 km a side.");
    expect(createJob).not.toHaveBeenCalled();
  });

  it("aborts the running job on unmount", async () => {
    let signal: AbortSignal | undefined;
    vi.mocked(createJob).mockResolvedValue({ job_id: "j1" });
    vi.mocked(pollJob).mockImplementation((_id, _onProgress, _ms, opts) => {
      signal = opts?.signal;
      return new Promise(() => {});
    });
    render(<Harness />);
    await act(async () => fireEvent.click(screen.getByText("go")));
    cleanup();
    expect(signal?.aborted).toBe(true);
  });
});

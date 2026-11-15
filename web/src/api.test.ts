import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FIXTURE_MESSAGE, TIMEOUT_MESSAGE, createJob, isResult, loadScorecard, loadStory, loadStoryIndex, pollJob } from "./api.ts";
import type { Job, Result } from "./types.ts";

const API = "https://api.example.test";

function sampleResult(overrides: Partial<Result> = {}): Result {
  return {
    bbox: [-119.37, 48.05, -118.72, 48.36],
    message: null,
    fixture: false,
    nisar: { track: 71, direction: "D", dates: ["2026-07-13", "2026-09-11"] },
    s1: { track: 166, dates: ["2026-07-11", "2026-09-09"] },
    overlays: {
      change_png: "kaiser/change.png",
      l_png: "kaiser/l.png",
      c_png: "kaiser/c.png",
      before_png: "kaiser/before.png",
      after_png: "kaiser/after.png",
      bounds: [
        [-119.4, 48.4],
        [-118.7, 48.4],
        [-118.7, 48.0],
        [-119.4, 48.0],
      ],
    },
    areas: [
      {
        id: "a1",
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
        agreement: "L",
        class: "burn",
        area_ha: 12,
        confidence: 0.9,
        confidence_label: "High",
        p_value: 0.001,
        change_date: "2026-09-11",
        evidence: [{ label: "NISAR HV change", value: -3.4, ci: [-3.8, -3.0], unit: "dB", note: "" }],
        plain_text: "Text.",
        series: { dates: ["2026-07-13"], HH: [null], HV: [-13], VV: [null], VH: [null] },
      },
    ],
    people: { svi_tracts: [] },
    exports: { geotiff: null, csv: null, notebook: null },
    ...overrides,
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function job(status: Job["status"], progress: number, message: string, result: Result | null = null): Job {
  return { job_id: "abc", status, progress, message, result };
}

/** Route fetch by URL suffix; unmatched URLs get a 404. */
function routeFetch(routes: Record<string, () => Response>) {
  const fn = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const key = Object.keys(routes).find((k) => url.endsWith(k));
    return key ? routes[key]() : new Response("Not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

describe("live API mode", () => {
  beforeEach(() => vi.stubEnv("VITE_API_URL", API));
  afterEach(() => vi.useRealTimers());

  it("pollJob resolves on done", async () => {
    const replies = [
      json(job("queued", 0, "Queued")),
      json(job("running", 0.45, "Reading passes")),
      json(job("done", 1, "Done", sampleResult({ overlays: { ...sampleResult().overlays, change_png: "/exports/abc/change.png" } }))),
    ];
    const fetchFn = vi.fn(async () => replies.shift()!);
    vi.stubGlobal("fetch", fetchFn);
    const seen: number[] = [];

    const result = await pollJob("abc", (j) => seen.push(j.progress), 0);

    expect(fetchFn).toHaveBeenCalledTimes(3);
    expect(String(fetchFn.mock.calls[0][0 as never])).toBe(`${API}/jobs/abc`);
    expect(seen).toEqual([0, 0.45, 1]);
    expect(result.areas[0].class).toBe("burn");
    // Path-absolute URLs from the API resolve against the API origin.
    expect(result.overlays.change_png).toBe(`${API}/exports/abc/change.png`);
  });

  it("pollJob rejects with server message on error", async () => {
    const msg = "No calibrated NISAR passes cover this box between 2026-06-01 and 2026-10-31.";
    vi.stubGlobal("fetch", vi.fn(async () => json(job("error", 0.1, msg))));

    await expect(pollJob("abc", () => {}, 0)).rejects.toThrow(msg);
  });

  it("pollJob survives a transient network failure", async () => {
    const replies: (() => Response)[] = [
      () => {
        throw new TypeError("Failed to fetch");
      },
      () => json(job("done", 1, "Done", sampleResult())),
    ];
    vi.stubGlobal("fetch", vi.fn(async () => replies.shift()!()));

    await expect(pollJob("abc", () => {}, 0)).resolves.toMatchObject({ fixture: false });
  });

  it("pollJob stops when aborted", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(job("running", 0.2, "Reading passes"))));
    const ctl = new AbortController();

    const p = pollJob("abc", () => ctl.abort(), 0, { signal: ctl.signal });

    await expect(p).rejects.toMatchObject({ name: "AbortError" });
  });

  it("pollJob gives up after timeoutMs with a readable message", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn(async () => json(job("running", 0.3, "Reading passes"))));

    const check = expect(pollJob("abc", () => {}, 1000, { timeoutMs: 5000 })).rejects.toThrow(TIMEOUT_MESSAGE);
    await vi.advanceTimersByTimeAsync(5000);
    await check;
  });

  it("pollJob's default deadline is 12 minutes", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn(async () => json(job("queued", 0, "Queued"))));
    let settled = false;

    const outcome = pollJob("abc", () => {}).then(
      () => "resolved",
      (e: Error) => e.message,
    );
    void outcome.finally(() => (settled = true));
    await vi.advanceTimersByTimeAsync(12 * 60_000 - 1000);
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(1000);
    expect(await outcome).toBe(TIMEOUT_MESSAGE);
  });

  it("createJob posts the box and returns the job id", async () => {
    const fetchFn = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => json({ job_id: "j1" }));
    vi.stubGlobal("fetch", fetchFn);

    await expect(createJob([-120, 47, -119.9, 47.1], ["2026-07-13", "2026-09-11"])).resolves.toEqual({ job_id: "j1" });
    const [url, init] = fetchFn.mock.calls[0];
    expect(String(url)).toBe(`${API}/jobs`);
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ bbox: [-120, 47, -119.9, 47.1], dates: ["2026-07-13", "2026-09-11"] });
  });

  it("createJob rejects with the server's readable detail", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ detail: "Boxes are limited to 20 km a side." }, 422)));
    await expect(createJob([-120, 47, -119, 48])).rejects.toThrow("Boxes are limited to 20 km a side.");

    vi.stubGlobal("fetch", vi.fn(async () => json({ detail: [{ loc: ["body", "bbox"], msg: "bbox must have 4 numbers" }] }, 422)));
    await expect(createJob([-120, 47, -119, 48])).rejects.toThrow("bbox must have 4 numbers");
  });
});

describe("static stories and scorecard", () => {
  it("loadStory falls back to fixture", async () => {
    const fetchFn = routeFetch({ "/fixtures/kaiser.json": () => json(sampleResult({ fixture: true })) });

    const story = await loadStory("kaiser");

    expect(fetchFn.mock.calls.map((c) => new URL(String(c[0])).pathname)).toEqual(["/stories/kaiser.json", "/fixtures/kaiser.json"]);
    expect(story.fixture).toBe(true);
    expect(story.message).toBe(FIXTURE_MESSAGE);
    // Relative overlay URLs resolve against the JSON file they came from.
    expect(new URL(story.overlays.l_png).pathname).toBe("/fixtures/kaiser/l.png");
  });

  it("loadStory falls back when the server answers with the HTML app shell", async () => {
    routeFetch({
      "/stories/kaiser.json": () => new Response("<!doctype html><html></html>", { status: 200, headers: { "Content-Type": "text/html" } }),
      "/fixtures/kaiser.json": () => json(sampleResult({ fixture: true })),
    });

    await expect(loadStory("kaiser")).resolves.toMatchObject({ fixture: true });
  });

  it("loadStory prefers the generated story", async () => {
    routeFetch({ "/stories/kaiser.json": () => json(sampleResult()), "/fixtures/kaiser.json": () => json(sampleResult({ fixture: true })) });

    const story = await loadStory("kaiser");

    expect(story.fixture).toBe(false);
    expect(story.message).toBeNull();
    expect(new URL(story.overlays.change_png).pathname).toBe("/stories/kaiser/change.png");
  });

  it("loadStory keeps a fixture's own message after the disclosure", async () => {
    routeFetch({ "/fixtures/edouard.json": () => json(sampleResult({ fixture: true, message: "No S1 pass during the flood." })) });

    const story = await loadStory("edouard");

    expect(story.message).toBe(`${FIXTURE_MESSAGE} No S1 pass during the flood.`);
  });

  it("loadStory rejects unknown ids and bad input", async () => {
    routeFetch({});
    await expect(loadStory("nowhere")).rejects.toThrow('Story "nowhere" is not available.');
    await expect(loadStory("../secrets")).rejects.toThrow("Invalid story id");
  });

  it("loadStoryIndex falls back to the fixture index", async () => {
    const entry = { id: "kaiser", title: "Kaiser Canyon Fire", place: "WA", dates: ["2026-07-13", "2026-09-11"], summary: "s" };
    routeFetch({ "/fixtures/index.json": () => json([entry]) });
    await expect(loadStoryIndex()).resolves.toEqual([{ ...entry, fixture: true }]);

    routeFetch({ "/stories/index.json": () => json([entry]), "/fixtures/index.json": () => json([entry]) });
    await expect(loadStoryIndex()).resolves.toEqual([{ ...entry, fixture: false }]);
  });

  it("loadScorecard returns null until the scorecard exists", async () => {
    routeFetch({});
    await expect(loadScorecard()).resolves.toBeNull();

    routeFetch({ "/scorecard.json": () => json({ n_sites: 300, classes: [], fusion: [], sites: [] }) });
    await expect(loadScorecard()).resolves.toMatchObject({ n_sites: 300 });
  });
});

describe("mock mode (VITE_API_URL unset)", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_API_URL", "");
    vi.useFakeTimers();
  });
  afterEach(() => vi.useRealTimers());

  it("resolves the nearest fixture after a simulated 3 s", async () => {
    const fetchFn = routeFetch({
      "/fixtures/clearcuts.json": () => json(sampleResult({ fixture: true, bbox: [-122.45, 46.55, -122.05, 46.8] })),
    });
    const { job_id } = await createJob([-122.3, 46.6, -122.2, 46.7]);
    const seen: Job[] = [];
    let done = false;

    const p = pollJob(job_id, (j) => seen.push(j)).then((r) => {
      done = true;
      return r;
    });
    await vi.advanceTimersByTimeAsync(2900);
    expect(done).toBe(false);
    await vi.advanceTimersByTimeAsync(200);

    const result = await p;
    expect(result.fixture).toBe(true);
    expect(fetchFn).toHaveBeenCalledTimes(1);
    expect(seen.at(-1)?.status).toBe("done");
    expect(result.message).toMatch(/^Demo mode: /);
    expect(result.message).toContain(FIXTURE_MESSAGE);
    expect(seen.map((j) => j.progress)).toEqual([...seen.map((j) => j.progress)].sort((a, b) => a - b));
  });
});

describe("mock mode warning", () => {
  it("warns once when a production build has no API URL", async () => {
    vi.stubEnv("VITE_API_URL", "");
    vi.stubEnv("PROD", true);
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});

    await createJob([-122.3, 46.6, -122.2, 46.7]);
    await createJob([-122.3, 46.6, -122.2, 46.7]);

    expect(warn).toHaveBeenCalledTimes(1);
  });
});

describe("isResult", () => {
  it("accepts a contract-shaped result and rejects junk", () => {
    expect(isResult(sampleResult())).toBe(true);
    expect(isResult({ ...sampleResult(), bbox: [1, 2, 3] })).toBe(false);
    expect(isResult({ ...sampleResult(), areas: [{ id: "x" }] })).toBe(false);
    expect(isResult("<html>")).toBe(false);
  });
});

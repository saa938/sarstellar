// Client for the job API (Task A7) and the static stories/scorecard files.
// VITE_API_URL unset or empty -> mock mode: jobs resolve to the nearest fixture after a simulated 3 s.
import type { Bbox, IsoDate, Job, Result, Scorecard, StoryIndexEntry } from "./types.ts";

const MOCK_DURATION_MS = 3000;
const MAX_POLL_FAILURES = 5;
const MOCK_MESSAGE = "Demo mode: no analysis server is configured, so this is a saved example, not a live analysis.";
const MOCK_STAGES: [number, string][] = [
  [0.1, "Finding NISAR and Sentinel-1 passes"],
  [0.45, "Reading passes"],
  [0.8, "Testing every 1-hectare block for change"],
  [0.9, "Explaining what changed"],
];
/** Fixture ids and their box centres [lon, lat], used to pick the nearest fixture in mock mode. */
const FIXTURE_CENTERS: Record<string, [number, number]> = {
  clearcuts: [-122.25, 46.675],
  kaiser: [-119.045, 48.207],
  edouard: [-94.225, 30.325],
};
const STORY_ID = /^[a-z0-9][a-z0-9_-]*$/;
const OVERLAY_KEYS = ["change_png", "l_png", "c_png", "before_png", "after_png"] as const;
const EXPORT_KEYS = ["geotiff", "csv", "notebook"] as const;

/** HTTP failure carrying the server's readable `detail`. */
export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function apiBase(): string {
  return (import.meta.env.VITE_API_URL ?? "").trim().replace(/\/+$/, "");
}

export function isMockMode(): boolean {
  return apiBase() === "";
}

/** Absolute URL of a file served with the web app (public/). */
function siteUrl(path: string): string {
  return new URL(import.meta.env.BASE_URL + path, globalThis.location?.href ?? "http://localhost/").href;
}

// ---------------------------------------------------------------- jobs

const mockJobs = new Map<string, Bbox>();
let mockSeq = 0;

export async function createJob(bbox: Bbox, dates?: [IsoDate, IsoDate], signal?: AbortSignal): Promise<{ job_id: string }> {
  if (!Array.isArray(bbox) || bbox.length !== 4 || !bbox.every(isNum)) throw new Error("A box needs four finite coordinates.");
  if (isMockMode()) {
    const job_id = `mock-${++mockSeq}`;
    mockJobs.set(job_id, bbox);
    return { job_id };
  }
  const res = await fetch(`${apiBase()}/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(dates ? { bbox, dates } : { bbox }),
    signal,
  });
  if (!res.ok) throw new ApiError(await errorDetail(res), res.status);
  const body: unknown = await res.json().catch(() => null);
  if (!isObj(body) || typeof body.job_id !== "string") throw new Error("The analysis server sent an unexpected reply.");
  return { job_id: body.job_id };
}

/**
 * Poll GET /jobs/{id} until the job is done (resolves with its Result) or errors
 * (rejects with the job's own message, shown verbatim in the UI).
 */
export async function pollJob(
  id: string,
  onProgress: (job: Job) => void,
  intervalMs = 1000,
  signal?: AbortSignal,
): Promise<Result> {
  if (isMockMode()) return pollMock(id, onProgress, signal);
  const base = apiBase();
  let failures = 0;
  for (;;) {
    throwIfAborted(signal);
    let job: Job;
    try {
      const res = await fetch(`${base}/jobs/${encodeURIComponent(id)}`, { signal });
      if (!res.ok) throw new ApiError(await errorDetail(res), res.status);
      const body: unknown = await res.json();
      if (!isJob(body)) throw new Error("The analysis server sent an unexpected reply.");
      job = body;
      failures = 0;
    } catch (err) {
      throwIfAborted(signal);
      // Network blips, 5xx and 429 are retried; 404 and other client errors are final.
      const transient = !(err instanceof ApiError) || err.status >= 500 || err.status === 429;
      if (!transient || ++failures >= MAX_POLL_FAILURES) throw err;
      await sleep(intervalMs, signal);
      continue;
    }
    onProgress(job);
    if (job.status === "done") {
      if (!isResult(job.result)) throw new Error("The analysis finished without a usable result.");
      return normalize(job.result, `${base}/`);
    }
    if (job.status === "error") throw new Error(job.message || "The analysis failed.");
    await sleep(intervalMs, signal);
  }
}

async function pollMock(id: string, onProgress: (job: Job) => void, signal?: AbortSignal): Promise<Result> {
  const bbox = mockJobs.get(id);
  if (!bbox) throw new Error(`Unknown job ${id}.`);
  const step = MOCK_DURATION_MS / MOCK_STAGES.length;
  for (const [progress, message] of MOCK_STAGES) {
    onProgress({ job_id: id, status: "running", progress, message, result: null });
    await sleep(step, signal);
  }
  const fixture = await loadFixture(nearestFixture(bbox));
  const result = { ...fixture, message: fixture.message ? `${MOCK_MESSAGE} ${fixture.message}` : MOCK_MESSAGE };
  onProgress({ job_id: id, status: "done", progress: 1, message: "Done", result });
  return result;
}

function nearestFixture([w, s, e, n]: Bbox): string {
  const lon = (w + e) / 2;
  const lat = (s + n) / 2;
  const dist = ([x, y]: [number, number]) => Math.hypot((x - lon) * Math.cos((lat * Math.PI) / 180), y - lat);
  return Object.keys(FIXTURE_CENTERS).reduce((a, b) => (dist(FIXTURE_CENTERS[b]) < dist(FIXTURE_CENTERS[a]) ? b : a));
}

// ---------------------------------------------------------------- static files

/** A precomputed story from /stories/{id}.json, falling back to /fixtures/{id}.json. */
export async function loadStory(id: string): Promise<Result> {
  if (!STORY_ID.test(id)) throw new Error(`Invalid story id: ${id}`);
  for (const dir of ["stories", "fixtures"]) {
    const url = siteUrl(`${dir}/${id}.json`);
    const data = await tryFetchJson(url);
    if (isResult(data)) return normalize(data, url);
  }
  throw new Error(`Story "${id}" is not available.`);
}

async function loadFixture(id: string): Promise<Result> {
  const url = siteUrl(`fixtures/${id}.json`);
  const data = await tryFetchJson(url);
  if (!isResult(data)) throw new Error(`Example "${id}" is not available.`);
  return normalize(data, url);
}

/** The stories list from /stories/index.json, falling back to /fixtures/index.json. */
export async function loadStoryIndex(): Promise<StoryIndexEntry[]> {
  for (const dir of ["stories", "fixtures"]) {
    const data = await tryFetchJson(siteUrl(`${dir}/index.json`));
    if (Array.isArray(data) && data.length > 0 && data.every(isStoryEntry)) return data;
  }
  return [];
}

/** The national scorecard, or null until Task C2 has written /scorecard.json. */
export async function loadScorecard(): Promise<Scorecard | null> {
  const data = await tryFetchJson(siteUrl("scorecard.json"));
  const ok = isObj(data) && isNum(data.n_sites) && Array.isArray(data.classes) && Array.isArray(data.fusion);
  return ok ? (data as unknown as Scorecard) : null;
}

// ---------------------------------------------------------------- helpers

/** JSON body, or undefined on network error, non-2xx, or non-JSON (e.g. an SPA index.html fallback). */
async function tryFetchJson(url: string): Promise<unknown> {
  try {
    const res = await fetch(url);
    return res.ok ? await res.json() : undefined;
  } catch {
    return undefined;
  }
}

async function errorDetail(res: Response): Promise<string> {
  const body: unknown = await res.json().catch(() => null);
  const detail = isObj(body) ? body.detail : undefined;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    const msgs = detail.map((d) => (isObj(d) ? d.msg : undefined)).filter((m): m is string => typeof m === "string");
    if (msgs.length) return msgs.join("; ");
  }
  return `The analysis server returned an error (HTTP ${res.status}).`;
}

/** Fill optional-ish fields and make overlay/export URLs absolute relative to where the JSON came from. */
function normalize(r: Result, base: string): Result {
  const abs = (u: string) => new URL(u, base).href;
  const overlays = { ...r.overlays };
  for (const k of OVERLAY_KEYS) overlays[k] = abs(overlays[k]);
  const ex: Record<string, unknown> = isObj(r.exports) ? r.exports : {};
  const exports = { geotiff: null, csv: null, notebook: null } as Result["exports"];
  for (const k of EXPORT_KEYS) {
    const u = ex[k];
    exports[k] = typeof u === "string" && u ? abs(u) : null;
  }
  return { ...r, message: r.message ?? null, s1: r.s1 ?? null, overlays, exports };
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(abortError(signal));
    const onAbort = () => {
      clearTimeout(timer);
      reject(abortError(signal!));
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

function throwIfAborted(signal?: AbortSignal): void {
  if (signal?.aborted) throw abortError(signal);
}

function abortError(signal: AbortSignal): Error {
  return signal.reason instanceof Error ? signal.reason : new DOMException("The operation was aborted.", "AbortError");
}

// ---------------------------------------------------------------- runtime shape checks

function isObj(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

function isNum(x: unknown): x is number {
  return typeof x === "number" && Number.isFinite(x);
}

function isLonLat(x: unknown): boolean {
  return Array.isArray(x) && x.length === 2 && x.every(isNum);
}

function isJob(x: unknown): x is Job {
  return isObj(x) && typeof x.status === "string" && ["queued", "running", "done", "error"].includes(x.status);
}

function isStoryEntry(x: unknown): x is StoryIndexEntry {
  return isObj(x) && typeof x.id === "string" && STORY_ID.test(x.id) && typeof x.title === "string";
}

function isChangeArea(a: unknown): boolean {
  if (!isObj(a) || !isObj(a.geometry) || !isObj(a.series)) return false;
  return (
    typeof a.id === "string" &&
    (a.geometry.type === "Polygon" || a.geometry.type === "MultiPolygon") &&
    Array.isArray(a.geometry.coordinates) &&
    (a.agreement === "L" || a.agreement === "C" || a.agreement === "both") &&
    typeof a.class === "string" &&
    isNum(a.area_ha) &&
    isNum(a.confidence) &&
    Array.isArray(a.evidence) &&
    typeof a.plain_text === "string" &&
    Array.isArray(a.series.dates)
  );
}

/** Structural check of a Result at the network boundary (not a full schema validation). */
export function isResult(x: unknown): x is Result {
  if (!isObj(x)) return false;
  const { bbox, nisar, s1, overlays, areas, people, message } = x;
  return (
    Array.isArray(bbox) &&
    bbox.length === 4 &&
    bbox.every(isNum) &&
    typeof x.fixture === "boolean" &&
    (message == null || typeof message === "string") &&
    isObj(nisar) &&
    isNum(nisar.track) &&
    Array.isArray(nisar.dates) &&
    (s1 == null || (isObj(s1) && Array.isArray(s1.dates))) &&
    isObj(overlays) &&
    OVERLAY_KEYS.every((k) => typeof overlays[k] === "string") &&
    Array.isArray(overlays.bounds) &&
    overlays.bounds.length === 4 &&
    overlays.bounds.every(isLonLat) &&
    Array.isArray(areas) &&
    areas.every(isChangeArea) &&
    isObj(people) &&
    Array.isArray(people.svi_tracts)
  );
}

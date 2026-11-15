// Data loading with graceful fallback: real bundles under /stages/ and /moves.json win; when they
// are missing (404, or the host answers with an HTML page) we fall back to the synthetic fixtures.

import type { MovesDoc, StageIndex, StageIndexEntry, StageMeta } from "./types";

const ROOT = import.meta.env.BASE_URL.replace(/\/?$/, "/");
export const REAL_BASE = `${ROOT}stages/`;
export const FIXTURE_BASE = `${ROOT}stages-fixture/`;

async function tryJSON<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url, { cache: "no-cache" });
    if (!res.ok) return null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("text/html")) return null;
    const text = await res.text();
    if (text.trimStart().startsWith("<")) return null;
    return JSON.parse(text) as T;
  } catch {
    return null;
  }
}

export interface IndexResult {
  index: StageIndex;
  base: string;
  fixture: boolean;
}

let indexPromise: Promise<IndexResult> | null = null;
let fixtureIndexPromise: Promise<StageIndex | null> | null = null;

function loadFixtureIndex() {
  fixtureIndexPromise ??= tryJSON<StageIndex>(`${FIXTURE_BASE}index.json`);
  return fixtureIndexPromise;
}

export function loadIndex(): Promise<IndexResult> {
  indexPromise ??= (async () => {
    const real = await tryJSON<StageIndex>(`${REAL_BASE}index.json`);
    if (real && Array.isArray(real.stages) && real.stages.length) {
      real.stages = sortStages(real.stages);
      return { index: real, base: REAL_BASE, fixture: !!real.fixture };
    }
    const fx = await loadFixtureIndex();
    return { index: fx ?? { stages: [] }, base: FIXTURE_BASE, fixture: true };
  })();
  return indexPromise;
}

function sortStages(st: StageIndexEntry[]) {
  return st
    .map((s, i) => ({ s, i }))
    .sort((a, b) => ((a.s as { order?: number }).order ?? 1000 + a.i) - ((b.s as { order?: number }).order ?? 1000 + b.i))
    .map((x) => x.s);
}

export interface MovesResult {
  doc: MovesDoc;
  fixture: boolean;
}

let movesPromise: Promise<MovesResult | null> | null = null;

export function loadMoves(): Promise<MovesResult | null> {
  movesPromise ??= (async () => {
    const real = await tryJSON<MovesDoc>(`${ROOT}moves.json`);
    if (real && real.floor && Array.isArray(real.moves)) return { doc: real, fixture: !!real.fixture };
    const fx = await tryJSON<MovesDoc>(`${ROOT}moves-fixture.json`);
    if (fx) return { doc: fx, fixture: true };
    return null;
  })();
  return movesPromise;
}

let proofPromise: Promise<Record<string, unknown> | null> | null = null;

export function loadProof(): Promise<Record<string, unknown> | null> {
  proofPromise ??= tryJSON<Record<string, unknown>>(`${ROOT}proof.json`);
  return proofPromise;
}

export interface StageResult {
  meta: StageMeta;
  base: string; // directory of this stage, ends with "/"
  root: string; // stages directory the index came from
  fixture: boolean;
  entry?: StageIndexEntry;
}

const stageCache = new Map<string, Promise<StageResult | null>>();

export function loadStage(id: string): Promise<StageResult | null> {
  let p = stageCache.get(id);
  if (!p) {
    p = (async () => {
      const { index, base, fixture } = await loadIndex();
      const entry = index.stages.find((s) => s.id === id);
      const tryBases: [string, boolean][] = entry ? [[base, fixture]] : [];
      if (base !== FIXTURE_BASE) tryBases.push([FIXTURE_BASE, true]);
      if (!entry && base === FIXTURE_BASE) tryBases.push([FIXTURE_BASE, true]);
      for (const [b, fx] of tryBases) {
        const meta = await tryJSON<StageMeta>(`${b}${encodeURIComponent(id)}/stage.json`);
        if (meta) {
          let e = entry;
          if (!e && b === FIXTURE_BASE) e = (await loadFixtureIndex())?.stages.find((s) => s.id === id);
          return { meta, base: `${b}${encodeURIComponent(id)}/`, root: b, fixture: fx || !!meta.fixture, entry: e };
        }
      }
      return null;
    })();
    stageCache.set(id, p);
  }
  return p;
}

export function assetUrl(base: string, rel: string) {
  if (/^https?:\/\//.test(rel) || rel.startsWith("/")) return rel;
  return base + rel;
}

/** Optional live API (comes later). */
export const API_URL: string | undefined = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") || undefined;

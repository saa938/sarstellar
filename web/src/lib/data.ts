// Data loading. The science track writes everything under web/public; the web only reads it.
// Real files win; when one is missing (404, or the host answers with an HTML page) we fall back.

import type { MovesDoc, StageIndex, StageIndexEntry, StageMeta } from "./types";
import type { StoryDoc } from "./story";

const ROOT = import.meta.env.BASE_URL.replace(/\/?$/, "/");
export const REAL_BASE = `${ROOT}stages/`;
export const FIXTURE_BASE = `${ROOT}stages-fixture/`;

export function publicUrl(rel: string) {
  if (/^https?:\/\//.test(rel) || rel.startsWith("/")) return rel;
  return ROOT + rel;
}

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

function sortStages(st: StageIndexEntry[]) {
  return st
    .map((s, i) => ({ s, i }))
    .sort((a, b) => ((a.s as { order?: number }).order ?? 1000 + a.i) - ((b.s as { order?: number }).order ?? 1000 + b.i))
    .map((x) => x.s);
}

export function loadIndex(): Promise<IndexResult> {
  indexPromise ??= (async () => {
    const real = await tryJSON<StageIndex>(`${REAL_BASE}index.json`);
    if (real && Array.isArray(real.stages) && real.stages.length) {
      real.stages = sortStages(real.stages);
      return { index: real, base: REAL_BASE, fixture: !!real.fixture };
    }
    const fx = await tryJSON<StageIndex>(`${FIXTURE_BASE}index.json`);
    return { index: fx ?? { stages: [] }, base: FIXTURE_BASE, fixture: true };
  })();
  return indexPromise;
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

export interface StoryResult {
  doc: StoryDoc;
  placeholder: boolean;
}

let storyPromise: Promise<StoryResult | null> | null = null;

/** story.json from the science track; a clearly labeled placeholder until it lands. */
export function loadStory(): Promise<StoryResult | null> {
  storyPromise ??= (async () => {
    const real = await tryJSON<StoryDoc>(`${ROOT}story/story.json`);
    if (real && real.hero) return { doc: real, placeholder: false };
    const ph = await tryJSON<StoryDoc>(`${ROOT}story-placeholder/story.json`);
    if (ph) return { doc: ph, placeholder: true };
    return null;
  })();
  return storyPromise;
}

export interface StageResult {
  meta: StageMeta;
  base: string; // directory of this stage, ends with "/"
  root: string;
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
      // real data wins outright: once a real index exists, synthetic stages are never shown
      if (!entry && base !== FIXTURE_BASE) return null;
      const meta = await tryJSON<StageMeta>(`${base}${encodeURIComponent(id)}/stage.json`);
      if (!meta) return null;
      return { meta, base: `${base}${encodeURIComponent(id)}/`, root: base, fixture: fixture || !!meta.fixture, entry };
    })();
    stageCache.set(id, p);
  }
  return p;
}

export function assetUrl(base: string, rel: string) {
  if (/^https?:\/\//.test(rel) || rel.startsWith("/")) return rel;
  return base + rel;
}

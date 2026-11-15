// Data loading with graceful fallback: real bundles under /stages/ and /moves.json win; when they
// are missing (404, or the host answers with an HTML page) we fall back to the synthetic fixtures.

import type { MovesDoc, StageIndex, StageIndexEntry, StageMeta } from "./types";

const ROOT = import.meta.env.BASE_URL.replace(/\/?$/, "/");

/** Live dance API: POST /dance, GET /dance/{id}, bundles at /dance/{id}/files/.
 *  Read from VITE_DANCE_API_URL (VITE_API_URL is ignored: in production it still points at the v1 API).
 *  Set VITE_DANCE_API_URL to "off" to hide live mode. */
const DANCE_API_DEFAULT = "https://tejas-16842--sarstellar-dance-live.us-east.modal.run";
const danceEnv = (import.meta.env.VITE_DANCE_API_URL as string | undefined)?.trim();
export const API_URL: string | undefined = danceEnv === "off" ? undefined : (danceEnv || DANCE_API_DEFAULT).replace(/\/$/, "");
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
  if (!p && id.startsWith("live:") && API_URL) {
    // a bundle computed on demand by the live API (same contract)
    const liveId = id.slice(5);
    const base = `${API_URL}/dance/${encodeURIComponent(liveId)}/files/`;
    p = tryJSON<StageMeta>(`${base}stage.json`).then((meta) => (meta ? { meta, base, root: base, fixture: !!meta.fixture } : null));
    stageCache.set(id, p);
  }
  if (!p) {
    p = (async () => {
      const { index, base, fixture } = await loadIndex();
      const entry = index.stages.find((s) => s.id === id);
      // real data wins outright: once a real index exists, synthetic stages are never shown
      const tryBases: [string, boolean][] = entry ? [[base, fixture]] : base === FIXTURE_BASE ? [[FIXTURE_BASE, true]] : [];
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


// ---------------------------------------------------------------- constellation

export interface ConstellationDoc {
  fixture?: boolean;
  file?: string;
  count: number;
  stages: string[];
  moves?: string[];
  layout?: string;
}

export interface Constellation {
  doc: ConstellationDoc;
  fixture: boolean;
  N: number;
  xy: Float32Array; // N x (x, y) in 0..1, y up
  move: Uint8Array;
  stage: Uint8Array;
  block: Uint32Array;
}

let constPromise: Promise<Constellation | null> | null = null;

export function loadConstellation(): Promise<Constellation | null> {
  constPromise ??= (async () => {
    let doc = await tryJSON<ConstellationDoc>(`${ROOT}constellation.json`);
    let fixture = false;
    let bin = `${ROOT}${doc?.file ?? "constellation.bin"}`;
    if (!doc) {
      doc = await tryJSON<ConstellationDoc>(`${ROOT}constellation-fixture.json`);
      fixture = true;
      bin = `${ROOT}${doc?.file ?? "constellation-fixture.bin"}`;
    }
    if (!doc) return null;
    const res = await fetch(bin);
    if (!res.ok) return null;
    const buf = await res.arrayBuffer();
    const N = doc.count;
    const dv = new DataView(buf);
    const xy = new Float32Array(N * 2);
    const move = new Uint8Array(N);
    const stage = new Uint8Array(N);
    const block = new Uint32Array(N);
    if (/interleav/i.test(doc.layout ?? "")) {
      // per point: x f32, y f32, move u8, stage u8, block u32 (14 bytes)
      for (let i = 0; i < N; i++) {
        const o = i * 14;
        xy[i * 2] = dv.getFloat32(o, true);
        xy[i * 2 + 1] = dv.getFloat32(o + 4, true);
        move[i] = dv.getUint8(o + 8);
        stage[i] = dv.getUint8(o + 9);
        block[i] = dv.getUint32(o + 10, true);
      }
    } else {
      for (let i = 0; i < N * 2; i++) xy[i] = dv.getFloat32(i * 4, true);
      const o1 = N * 8;
      for (let i = 0; i < N; i++) move[i] = dv.getUint8(o1 + i);
      const o2 = o1 + N;
      for (let i = 0; i < N; i++) stage[i] = dv.getUint8(o2 + i);
      const o3 = o2 + N;
      for (let i = 0; i < N; i++) block[i] = dv.getUint32(o3 + i * 4, true);
    }
    return { doc, fixture: fixture || !!doc.fixture, N, xy, move, stage, block };
  })();
  return constPromise;
}

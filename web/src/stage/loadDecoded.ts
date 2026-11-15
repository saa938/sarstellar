import { assetUrl, loadIndex, loadMoves, loadStage, type IndexResult, type MovesResult, type StageResult } from "../lib/data";
import { DEFAULT_FLOOR, ZONE_STARLIGHT, hexToRgb } from "../lib/moves";
import type { FloorSpec } from "../lib/types";
import { decodeStage, type DecodeResult } from "./decoded";

export interface Loaded {
  res: StageResult;
  moves: MovesResult | null;
  index: IndexResult;
  data: DecodeResult;
  floor: FloorSpec;
  hhOnly: boolean;
}

const cache = new Map<string, Promise<Loaded>>();

/** Load stage.json + moves.json and decode blocks.bin (cached per stage id). */
export function loadDecoded(id: string, onStep?: (s: string) => void): Promise<Loaded> {
  let p = cache.get(id);
  if (p) return p;
  p = (async () => {
    const [res, moves, index] = await Promise.all([loadStage(id), loadMoves(), loadIndex()]);
    if (!res) throw new Error(`There is no stage called "${id}" yet.`);
    const meta = res.meta;
    const floor = moves?.doc.floor ?? DEFAULT_FLOOR;
    const P = meta.blocks.pols.length;
    const hhOnly = P === 1 || !meta.blocks.pols.includes("HV");
    onStep?.(`Reading ${(meta.grid.nx * meta.grid.ny).toLocaleString("en-US")} hectares across ${meta.dates.length} passes`);
    const zoneTints: Record<string, [number, number, number]> = {};
    for (const [k, v] of Object.entries(ZONE_STARLIGHT)) zoneTints[k] = hexToRgb(v);
    const data = await decodeStage({
      url: assetUrl(res.base, meta.blocks.file),
      movesUrl: meta.moves ? assetUrl(res.base, meta.moves.file) : null,
      nMoves: meta.moves?.ids.length ?? 0,
      T: meta.dates.length,
      P,
      nx: meta.grid.nx,
      ny: meta.grid.ny,
      scale: meta.blocks.scale,
      offset: meta.blocks.offset,
      nodata: meta.blocks.nodata,
      corners: meta.corners,
      zones: floor.zones.map((z) => ({ id: z.id, center: z.center })),
      zoneTints,
      hhOnly,
    });
    return { res, moves, index, data, floor, hhOnly };
  })();
  p.catch(() => cache.delete(id));
  cache.set(id, p);
  return p;
}

/** Colors per block for a floor without selection (moves if present, else starting surface). */
export function baseState(L: Loaded, mode: "moves" | "zone" = "moves", highlight: number[] = []) {
  const { data, res } = L;
  const K = data.K;
  const out = new Uint8Array(K * 4);
  const ids = res.meta.moves?.ids;
  const useMoves = mode === "moves" && data.move && ids;
  const rgb = ids ? ids.map((m) => lightenHex(m)) : [];
  const hl = new Set(highlight);
  for (let k = 0; k < K; k++) {
    let r = data.tint[k * 3];
    let g = data.tint[k * 3 + 1];
    let b = data.tint[k * 3 + 2];
    if (useMoves) {
      const m = data.move![k];
      if (m > 0 && m < rgb.length) [r, g, b] = rgb[m];
      else {
        r *= 0.78;
        g *= 0.78;
        b *= 0.82;
      }
    }
    out[k * 4] = r;
    out[k * 4 + 1] = g;
    out[k * 4 + 2] = b;
    out[k * 4 + 3] = hl.has(k) ? 2 : 0;
  }
  return out;
}

import { MOVE_COLORS, lighten } from "../lib/moves";
function lightenHex(id: string): [number, number, number] {
  return lighten(hexToRgb(MOVE_COLORS[id] || "#999999"), 0.18);
}

import type { LonLat } from "../lib/types";

export interface DecodeRequest {
  url: string;
  movesUrl: string | null;
  nMoves: number;
  T: number;
  P: number;
  nx: number;
  ny: number;
  scale: number;
  offset: number;
  nodata: number;
  corners: [LonLat, LonLat, LonLat, LonLat];
  zones: { id: string; center: [number, number] }[];
  zoneTints: Record<string, [number, number, number]>;
  hhOnly: boolean;
}

export interface DecodeResult {
  K: number;
  T: number;
  nx: number;
  ny: number;
  /** grid index n (row * nx + col) of each kept block k */
  idx: Uint32Array;
  /** k for each grid index, -1 when the block has no data */
  nToK: Int32Array;
  /** floor position per pass: [(t * K + k) * 2] = x (HH dB), +1 = y (HV dB, or HH change for HH-only) */
  xy: Float32Array;
  /** 1 when the pass had real data for the block (before gap filling) */
  valid: Uint8Array;
  /** starlight tint per block from its starting zone */
  tint: Uint8Array;
  zone: Uint8Array;
  lonlat: Float32Array;
  medX: Float32Array;
  medY: Float32Array;
  move: Uint8Array | null;
  conf: Uint8Array | null;
  beat: Uint8Array | null;
  moveCounts: number[] | null;
  /** HH-only stages: the dB range both floor axes use */
  range: [number, number] | null;
}

export function decodeStage(req: DecodeRequest): Promise<DecodeResult> {
  return new Promise((resolve, reject) => {
    const w = new Worker(new URL("../workers/blocks.worker.ts", import.meta.url), { type: "module" });
    w.onmessage = (ev: MessageEvent<{ ok: boolean; data?: DecodeResult; error?: string }>) => {
      w.terminate();
      if (ev.data.ok && ev.data.data) resolve(ev.data.data);
      else reject(new Error(ev.data.error || "decode failed"));
    };
    w.onerror = (e) => {
      w.terminate();
      reject(new Error(e.message || "worker error"));
    };
    w.postMessage(req);
  });
}

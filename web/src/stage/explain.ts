// Plain-language reading of one hectare's trajectory. When the science track ships moves, the
// move's own physics text leads; otherwise this is a transparent textbook reading of the numbers
// (labeled as such in the UI), never a model claim.

import type { DecodeResult } from "./decoded";
import type { FloorZone, MoveDef } from "../lib/types";
import { fmtDate } from "../lib/format";

export interface Reading {
  headline: string;
  sentences: string[];
  kind: "move" | "textbook";
}

function zoneName(z: FloorZone | undefined) {
  if (!z) return "an unnamed part of the floor";
  const main = z.label.split(":")[0].trim().toLowerCase();
  return main;
}

function nearestZone(zones: FloorZone[], x: number, y: number) {
  let best: FloorZone | undefined;
  let bd = Infinity;
  for (const z of zones) {
    const d = (x - z.center[0]) ** 2 + (y - z.center[1]) ** 2;
    if (d < bd) {
      bd = d;
      best = z;
    }
  }
  return best;
}

const db = (v: number) => `${Math.abs(v).toFixed(1)} dB`;

export function readBlock(d: DecodeResult, k: number, dates: string[], zones: FloorZone[], hhOnly: boolean, move: MoveDef | null): Reading {
  const T = d.T;
  const K = d.K;
  const hh: number[] = [];
  const hv: number[] = [];
  const ok: boolean[] = [];
  for (let t = 0; t < T; t++) {
    // HH-only floors keep HH of the pass in y (x is the first pass)
    hh.push(d.xy[(t * K + k) * 2 + (hhOnly ? 1 : 0)]);
    hv.push(hhOnly ? 0 : d.xy[(t * K + k) * 2 + 1]);
    ok.push(!!d.valid[t * K + k]);
  }
  // largest single step between consecutive valid passes (by combined size)
  let bestT = -1;
  let bestMag = 0;
  let prev = -1;
  for (let t = 0; t < T; t++) {
    if (!ok[t]) continue;
    if (prev >= 0) {
      const mag = Math.hypot(hh[t] - hh[prev], hhOnly ? 0 : hv[t] - hv[prev]);
      if (mag > bestMag) {
        bestMag = mag;
        bestT = t;
      }
    }
    prev = t;
  }
  let p0 = bestT - 1;
  while (p0 > 0 && !ok[p0]) p0--;
  const dHH = bestT >= 0 ? hh[bestT] - hh[p0] : 0;
  const dHV = bestT >= 0 ? hv[bestT] - hv[p0] : 0;

  const startZ = hhOnly ? undefined : nearestZone(zones, (hh[0] + hh[1 % T]) / 2, (hv[0] + hv[1 % T]) / 2);
  const endZ = hhOnly ? undefined : nearestZone(zones, (hh[T - 1] + hh[Math.max(0, T - 2)]) / 2, (hv[T - 1] + hv[Math.max(0, T - 2)]) / 2);

  if (move) {
    const stepText =
      bestT >= 0 && bestMag > 1.5
        ? `Its biggest step came on ${fmtDate(dates[bestT])}: HH ${dHH >= 0 ? "rose" : "fell"} ${db(dHH)}${hhOnly ? "" : ` and HV ${dHV >= 0 ? "rose" : "fell"} ${db(dHV)}`}.`
        : "It never moves farther than the speckle noise.";
    const phys = move.physics.split(/(?<=\.)\s+/)[0];
    return { headline: move.name, sentences: [stepText, phys], kind: "move" };
  }

  // textbook reading
  let reading = "a step within the range of speckle noise";
  if (bestMag > 1.5) {
    if (hhOnly) reading = dHH < -3 ? "how wet, melting snow absorbs the pulse" : dHH > 3 ? "how rough bare ice or a refrozen crust sends more back" : "a modest change";
    else if (dHV < -2.5 && Math.abs(dHH) < Math.abs(dHV) * 0.75) reading = "the signature of canopy being removed";
    else if (dHH > 2.5 && Math.abs(dHV) < 1.5) reading = "the signature of water under a canopy (double bounce)";
    else if (dHH < -3 && dHV < -3) reading = "the signature of open water appearing";
    else if (dHH > 3 && dHV > 3) reading = "the signature of water draining away";
    else if (dHV > 2 && dHH > -1) reading = "what growing vegetation looks like";
    else if (dHH > 0.8 && dHV > 0.5 && dHH < 3.5) reading = "what rain-wet soil looks like";
  }
  const where = hhOnly
    ? "This hectare is measured with HH only, as NISAR does over ice."
    : startZ && endZ && startZ.id !== endZ.id
      ? `It starts among ${zoneName(startZ)} and ends among ${zoneName(endZ)}.`
      : `It starts and ends among ${zoneName(startZ)}.`;
  const step =
    bestT >= 0 && bestMag > 1.5
      ? `Its biggest step came on ${fmtDate(dates[bestT])}: HH ${dHH >= 0 ? "rose" : "fell"} ${db(dHH)}${hhOnly ? "" : ` and HV ${dHV >= 0 ? "rose" : "fell"} ${db(dHV)}`}, ${reading}.`
      : "It never moves farther than the speckle noise, the grain every radar image carries.";
  return { headline: startZ && endZ && startZ.id !== endZ.id ? "A hectare on the move" : "A hectare holding its place", sentences: [where, step], kind: "textbook" };
}

import { useEffect, useState } from "react";
import type { Clock } from "./clock";

/** React state that changes only on whole passes (not every frame). */
export function useClockBeat(clock: Clock) {
  const [state, setState] = useState({ beat: clock.beat, playing: clock.playing, tempo: clock.tempo });
  useEffect(() => clock.onBeat((beat, playing) => setState({ beat, playing, tempo: clock.tempo })), [clock]);
  return state;
}

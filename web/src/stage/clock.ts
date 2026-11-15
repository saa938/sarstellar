// The playback clock. Time t runs from 0 to T-1 in beats (passes). It never goes through React
// state: renderers subscribe and draw on every frame; React only hears about whole-beat changes.

export type Tempo = "slow" | "normal" | "fast";
export const TEMPO_SPB: Record<Tempo, number> = { slow: 1.7, normal: 0.95, fast: 0.45 };

export interface Frame {
  t: number;
  i0: number;
  i1: number;
  f: number;
  e: number;
  head: number;
  playing: boolean;
}

export function ease(f: number) {
  // smootherstep: dots accelerate off one beat and settle on the next
  return f * f * f * (f * (f * 6 - 15) + 10);
}

export const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export class Clock {
  T: number;
  t = 0;
  playing = false;
  tempo: Tempo = "normal";
  loop = true;
  holdBeats = new Set<number>();
  private raf = 0;
  private last = 0;
  private holdUntil = 0;
  private lastBeat = -1;
  private frameFns = new Set<(f: Frame) => void>();
  private beatFns = new Set<(beat: number, playing: boolean) => void>();

  constructor(T: number) {
    this.T = Math.max(1, T);
  }

  frame(): Frame {
    const T = this.T;
    const t = Math.min(Math.max(this.t, 0), T - 1);
    const i0 = Math.min(Math.floor(t), T - 1);
    const i1 = Math.min(i0 + 1, T - 1);
    const f = t - i0;
    const e = prefersReducedMotion() && this.playing ? (f > 0.5 ? 1 : 0) : ease(f);
    return { t, i0, i1, f, e, head: i0 + e, playing: this.playing };
  }

  get beat() {
    return Math.min(this.T - 1, Math.round(this.t));
  }

  subscribe(fn: (f: Frame) => void) {
    this.frameFns.add(fn);
    fn(this.frame());
    return () => {
      this.frameFns.delete(fn);
    };
  }

  onBeat(fn: (beat: number, playing: boolean) => void) {
    this.beatFns.add(fn);
    return () => {
      this.beatFns.delete(fn);
    };
  }

  invalidate() {
    if (!this.raf) this.raf = requestAnimationFrame(this.tick);
  }

  play() {
    if (this.T < 2) return;
    if (this.t >= this.T - 1 - 1e-6) this.t = 0;
    this.playing = true;
    this.last = performance.now();
    this.emitBeat(true);
    if (!this.raf) this.raf = requestAnimationFrame(this.tick);
  }

  pause() {
    this.playing = false;
    this.emitBeat(true);
    this.invalidate();
  }

  toggle() {
    if (this.playing) this.pause();
    else this.play();
  }

  seek(t: number) {
    this.t = Math.min(Math.max(t, 0), this.T - 1);
    this.holdUntil = 0;
    this.emitBeat();
    this.invalidate();
  }

  step(d: number) {
    this.pause();
    this.seek(Math.round(this.t) + d);
  }

  setTempo(tp: Tempo) {
    this.tempo = tp;
    this.emitBeat(true);
  }

  destroy() {
    cancelAnimationFrame(this.raf);
    this.raf = 0;
    this.playing = false;
    this.frameFns.clear();
    this.beatFns.clear();
  }

  private emitBeat(force = false) {
    const b = this.beat;
    if (force || b !== this.lastBeat) {
      this.lastBeat = b;
      for (const fn of this.beatFns) fn(b, this.playing);
    }
  }

  private tick = (now: number) => {
    this.raf = 0;
    if (this.playing) {
      const dt = Math.min(0.1, (now - this.last) / 1000);
      this.last = now;
      if (now < this.holdUntil) {
        // holding on a story beat or at the end
      } else if (this.t >= this.T - 1 - 1e-6) {
        if (this.holdUntil > 0) {
          this.holdUntil = 0;
          if (this.loop) this.t = 0;
          else this.playing = false;
        } else {
          this.holdUntil = now + 1600;
        }
      } else {
        const before = this.t;
        let next = before + dt / TEMPO_SPB[this.tempo];
        const nb = Math.floor(next);
        if (nb > Math.floor(before) && this.holdBeats.has(nb)) {
          next = nb;
          this.holdUntil = now + 1500;
        }
        this.t = Math.min(next, this.T - 1);
        if (this.t >= this.T - 1 - 1e-6) this.holdUntil = now + 1600;
      }
      this.emitBeat();
    }
    const fr = this.frame();
    for (const fn of this.frameFns) fn(fr);
    if (this.playing) this.raf = requestAnimationFrame(this.tick);
  };
}

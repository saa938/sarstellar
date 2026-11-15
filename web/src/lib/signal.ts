export interface Signal<T> {
  get(): T;
  set(v: T): void;
  subscribe(fn: (v: T) => void): () => void;
}

export function signal<T>(initial: T): Signal<T> {
  let v = initial;
  const fns = new Set<(v: T) => void>();
  return {
    get: () => v,
    set(nv: T) {
      if (Object.is(nv, v)) return;
      v = nv;
      for (const f of fns) f(v);
    },
    subscribe(fn) {
      fns.add(fn);
      return () => {
        fns.delete(fn);
      };
    },
  };
}

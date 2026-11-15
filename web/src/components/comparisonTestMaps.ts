// Test doubles for MapLibre and maplibre-gl-compare: happy-dom has no WebGL, so component tests swap these in
// with vi.mock (see ViewModes.test.tsx). They record what the components asked for.
type Handler = () => void;

export interface CameraLike {
  center?: { lng: number; lat: number };
  zoom?: number;
  bearing?: number;
  pitch?: number;
}

export class FakeMap {
  static instances: FakeMap[] = [];
  readonly options: Record<string, unknown>;
  removed = false;
  controls = 0;
  resizes = 0;
  center = { lng: 0, lat: 0 };
  zoom = 1;
  bearing = 0;
  pitch = 0;
  private handlers = new Map<string, Set<Handler>>();

  constructor(options: Record<string, unknown>) {
    this.options = options;
    FakeMap.instances.push(this);
  }

  on(type: string, fn: Handler) {
    if (!this.handlers.has(type)) this.handlers.set(type, new Set());
    this.handlers.get(type)!.add(fn);
    return this;
  }

  off(type: string, fn: Handler) {
    this.handlers.get(type)?.delete(fn);
    return this;
  }

  fire(type: string) {
    for (const fn of [...(this.handlers.get(type) ?? [])]) fn();
  }

  listenerCount(type: string) {
    return this.handlers.get(type)?.size ?? 0;
  }

  addControl() {
    this.controls++;
    return this;
  }

  remove() {
    this.removed = true;
  }

  resize() {
    this.resizes++;
    return this;
  }

  getContainer() {
    return this.options.container as HTMLElement;
  }

  getCenter() {
    return this.center;
  }

  getZoom() {
    return this.zoom;
  }

  getBearing() {
    return this.bearing;
  }

  getPitch() {
    return this.pitch;
  }

  /** Like MapLibre: moving the camera fires "move" synchronously. */
  jumpTo(o: CameraLike) {
    if (o.center) this.center = o.center;
    if (o.zoom !== undefined) this.zoom = o.zoom;
    if (o.bearing !== undefined) this.bearing = o.bearing;
    if (o.pitch !== undefined) this.pitch = o.pitch;
    this.fire("move");
    return this;
  }

  /** The image URL of the radar overlay in this map's style. */
  get radarUrl(): string {
    const style = this.options.style as { sources: Record<string, { url?: string }> };
    return style.sources.radar.url ?? "";
  }

  /** Agreement values of the change areas outlined on this map. */
  get outlined(): string[] {
    const style = this.options.style as {
      sources: Record<string, { data?: { features: { properties: { agreement: string } }[] } }>;
    };
    return (style.sources.areas.data?.features ?? []).map((f) => f.properties.agreement);
  }
}

export class FakeCompare {
  static instances: FakeCompare[] = [];
  removed = false;
  slider: number | null = null;
  readonly a: FakeMap;
  readonly b: FakeMap;
  readonly container: HTMLElement;
  private slideListener?: (event: { currentPosition: number }) => void;

  constructor(a: FakeMap, b: FakeMap, container: HTMLElement) {
    this.a = a;
    this.b = b;
    this.container = container;
    FakeCompare.instances.push(this);
  }

  setSlider(x: number) {
    this.slider = x;
  }

  on(_event: string, listener: (event: { currentPosition: number }) => void) {
    this.slideListener = listener;
    return this;
  }

  slide(position: number) {
    this.slideListener?.({ currentPosition: position });
  }

  remove() {
    this.removed = true;
  }
}

export class FakeNavigationControl {}

export function resetFakes(): void {
  FakeMap.instances = [];
  FakeCompare.instances = [];
}

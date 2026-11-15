// Types for the v2 data contract (docs/v2/CONTRACT.md). The science track writes these files;
// the web only reads them.

export type LonLat = [number, number];

export interface StageIndexEntry {
  id: string;
  name: string;
  country: string;
  center: LonLat;
  move: string;
  title: string;
  teaser: string;
  n_passes: number;
  first: string;
  last: string;
  thumb: string;
}

export interface StageIndex {
  generated_at?: string;
  fixture?: boolean;
  stages: StageIndexEntry[];
}

export interface StoryBeat {
  date: string;
  caption: string;
}

export interface StageMeta {
  id: string;
  fixture?: boolean;
  name: string;
  country: string;
  bbox: [number, number, number, number];
  corners: [LonLat, LonLat, LonLat, LonLat];
  grid: { nx: number; ny: number; res_m: number; epsg: number };
  stack: {
    track?: number;
    direction?: string;
    bandwidth_mhz?: number;
    mode?: string;
    pols?: string[];
    crid?: string;
    n_granules?: number;
  };
  dates: string[];
  blocks: {
    file: string;
    encoding: string;
    scale: number;
    offset: number;
    nodata: number;
    layout: string;
    pols: string[];
  };
  images?: {
    res_m: number;
    nx: number;
    ny: number;
    files: string[];
    thumb?: string;
  } | null;
  moves: null | {
    file: string;
    ids: string[];
    layout: string;
    note?: string;
  };
  story?: {
    title?: string;
    lede?: string;
    body?: string[];
    beats?: StoryBeat[];
    highlight?: { blocks: number[]; label?: string } | null;
  } | null;
  sources?: { name: string; url?: string }[];
  stats?: { valid_blocks?: number; km2?: number };
}

export interface FloorAxis {
  pol: string;
  min: number;
  max: number;
}

export interface FloorZone {
  id: string;
  label: string;
  center: [number, number];
}

export interface FloorSpec {
  x: FloorAxis;
  y: FloorAxis;
  zones: FloorZone[];
}

export interface PathPoint {
  HH: number;
  HV: number | null;
}

export interface MoveDef {
  id: string;
  name: string;
  what: string;
  physics: string;
  carried_by: string[];
  path: PathPoint[];
  metrics: unknown;
  stages: string[];
  future: string;
}

export interface MovesDoc {
  fixture?: boolean;
  floor: FloorSpec;
  moves: MoveDef[];
}

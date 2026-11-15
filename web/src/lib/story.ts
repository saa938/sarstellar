// story.json, written by the science track (web/public/story/story.json). Image paths are
// relative to web/public.

export interface StoryFrame {
  date: string;
  image: string;
}

export interface StoryChip {
  id: string;
  label: string;
  place: string;
  date: string;
  image: string;
  HH: number;
  HV: number;
  text: string;
}

export interface PathPoint2 {
  date: string;
  HH: number;
  HV?: number | null;
}

export type Measure = string | number | { value: string | number; unit?: string; label?: string };

export interface StoryExample {
  id: string;
  kicker: string;
  title: string;
  text: string;
  measure?: Measure;
  channel?: string;
  before: StoryFrame;
  after: StoryFrame;
  path?: PathPoint2[];
  cloud_before?: number[][];
  cloud_after?: number[][];
  one_d?: boolean;
  series?: { date: string; HH: number }[];
}

export interface ProofItem {
  id: string;
  kind: "dots" | "bars";
  statement: string;
  model?: number;
  baseline?: number;
  model_label?: string;
  baseline_label?: string;
  bars?: { label: string; value: number }[];
  detail?: string;
}

export interface StoryDoc {
  placeholder?: boolean;
  hero: { title: string; subtitle: string; place: string; frames: StoryFrame[] };
  channels: { title: string; text: string[]; chips: StoryChip[]; cloud: number[][] };
  examples: StoryExample[];
  proof: { title: string; intro?: string; items: ProofItem[]; limits: string[] };
  applications: { title: string; text: string }[];
}

// Start-up options read from the page URL, so the story site can link to or embed the map at a place.
// ?story=<id> opens a saved example; ?place=<story-site place id> maps to its example if one exists;
// ?bbox=w,s,e,n frames the map on that box (ready to draw); ?embed=1 hides the site header.
export type BBox = [number, number, number, number];

const PLACE_STORY: Record<string, string> = { morton: "clearcuts", kaiser: "kaiser", edouard: "edouard" };

export interface Launch {
  embed: boolean;
  story: string | null;
  focus: BBox | null;
}

export function parseLaunch(search: string): Launch {
  const p = new URLSearchParams(search);
  const nums = (p.get("bbox") ?? "").split(",").map(Number);
  const ok = nums.length === 4 && nums.every(Number.isFinite) && nums[0] < nums[2] && nums[1] < nums[3];
  return {
    embed: p.get("embed") === "1",
    story: p.get("story") ?? PLACE_STORY[p.get("place") ?? ""] ?? null,
    focus: ok ? (nums as BBox) : null,
  };
}

export const LAUNCH: Launch = parseLaunch(typeof window === "undefined" ? "" : window.location.search);

import { describe, expect, it } from "vitest";
import { parseLaunch } from "./launch.ts";

describe("parseLaunch", () => {
  it("maps story-site places to saved examples", () => {
    expect(parseLaunch("?place=morton&embed=1")).toEqual({ embed: true, story: "clearcuts", focus: null });
    expect(parseLaunch("?story=kaiser").story).toBe("kaiser");
  });
  it("frames a valid bbox and ignores a bad one", () => {
    expect(parseLaunch("?place=iowa&bbox=-93.7,41.9,-93.4,42.1")).toEqual({
      embed: false, story: null, focus: [-93.7, 41.9, -93.4, 42.1],
    });
    expect(parseLaunch("?bbox=1,2,0,3").focus).toBeNull();
    expect(parseLaunch("").story).toBeNull();
  });
});

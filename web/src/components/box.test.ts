import { describe, expect, it } from "vitest";
import type { Bbox } from "../types.ts";
import {
  EMPTY_BOX_MESSAGE,
  OUTSIDE_US_MESSAGE,
  OVERSIZE_MESSAGE,
  bboxFromRing,
  boxSize,
  formatSize,
  validateBox,
} from "./box.ts";

// Near the Clearcuts fixture: 0.1° of longitude at 46.65° N is ~7.6 km, 0.05° of latitude is ~5.6 km.
const SMALL: Bbox = [-122.3, 46.65, -122.2, 46.7];
// 0.3° x 0.2° at the same latitude: ~22.9 km wide, ~22.2 km tall.
const OVERSIZE: Bbox = [-122.3, 46.6, -122.0, 46.8];

describe("boxSize", () => {
  it("measures width along the parallel and height along the meridian", () => {
    const { widthKm, heightKm, areaKm2 } = boxSize(SMALL);
    expect(widthKm).toBeCloseTo(7.63, 1);
    expect(heightKm).toBeCloseTo(5.56, 1);
    expect(areaKm2).toBeCloseTo(widthKm * heightKm, 0);
  });

  it("uses the wider (equator-side) edge so the readout never under-reports", () => {
    const south = boxSize([-100, 30, -99.9, 30.01]).widthKm;
    const north = boxSize([-100, 29.99, -99.9, 30]).widthKm;
    expect(south).toBeLessThan(north);
  });
});

describe("validateBox", () => {
  it("accepts a small US box", () => {
    expect(validateBox(SMALL)).toBeNull();
  });

  it("rejects a box over 20 km a side with the exact message", () => {
    expect(validateBox(OVERSIZE)).toBe(OVERSIZE_MESSAGE);
    expect(OVERSIZE_MESSAGE).toBe("Boxes are limited to 20 km a side.");
  });

  it("rejects a tall, thin box whose height alone is over 20 km", () => {
    expect(validateBox([-122.3, 46.5, -122.29, 46.7])).toBe(OVERSIZE_MESSAGE);
  });

  it("rejects degenerate or inverted boxes", () => {
    expect(validateBox([-122.3, 46.6, -122.3, 46.7])).toBe(EMPTY_BOX_MESSAGE);
    expect(validateBox([-122.2, 46.6, -122.3, 46.7])).toBe(EMPTY_BOX_MESSAGE);
    expect(validateBox([-122.3, Number.NaN, -122.2, 46.7])).toBe(EMPTY_BOX_MESSAGE);
  });

  it("rejects boxes outside the US bounds", () => {
    expect(validateBox([2.3, 48.8, 2.4, 48.85])).toBe(OUTSIDE_US_MESSAGE);
    expect(validateBox([-60.05, 45, -59.95, 45.05])).toBe(OUTSIDE_US_MESSAGE);
  });
});

describe("bboxFromRing", () => {
  it("returns [w, s, e, n] from a rectangle ring in any corner order", () => {
    const ring = [
      [-122.2, 46.7],
      [-122.3, 46.7],
      [-122.3, 46.65],
      [-122.2, 46.65],
      [-122.2, 46.7],
    ];
    expect(bboxFromRing(ring)).toEqual(SMALL);
  });
});

describe("formatSize", () => {
  it("shows both sides and the area", () => {
    expect(formatSize(boxSize(SMALL))).toBe("7.6 × 5.6 km · 42 km²");
  });
});

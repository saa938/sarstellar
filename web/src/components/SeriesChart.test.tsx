import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { Series } from "../types.ts";
import SeriesChart from "./SeriesChart.tsx";

afterEach(cleanup);

const nulls = [null, null, null, null];
const SPANS_GAP: Series = {
  dates: ["2026-07-13", "2026-07-25", "2026-08-18", "2026-08-30"],
  HH: [-8.2, -8.0, -9.8, -9.7],
  HV: [-13.1, -13.0, -17.0, -17.2],
  VV: nulls,
  VH: nulls,
};

describe("SeriesChart", () => {
  it("shades the NISAR gap when the series spans 2026-07-27 to 2026-08-10", () => {
    const { container } = render(<SeriesChart series={SPANS_GAP} changeDate="2026-08-18" />);
    expect(container.querySelector(".sc-gap")).not.toBeNull();
    expect(screen.getByText("No NISAR data")).toBeTruthy();
  });

  it("does not shade the gap when the series is outside it", () => {
    const series: Series = { ...SPANS_GAP, dates: ["2026-08-26", "2026-09-07", "2026-09-19", "2026-10-01"] };
    const { container } = render(<SeriesChart series={series} />);
    expect(container.querySelector(".sc-gap")).toBeNull();
    expect(screen.queryByText("No NISAR data")).toBeNull();
  });

  it("lists only the bands that have values", () => {
    render(<SeriesChart series={{ ...SPANS_GAP, HH: nulls, VH: [null, -12, -12.5, null] }} />);
    expect(screen.getByText("NISAR HV")).toBeTruthy();
    expect(screen.getByText("Sentinel-1 VH")).toBeTruthy();
    expect(screen.queryByText("NISAR HH")).toBeNull();
    expect(screen.queryByText("Sentinel-1 VV")).toBeNull();
  });

  it("says so when there is nothing to plot", () => {
    render(<SeriesChart series={{ dates: [], HH: [], HV: [], VV: [], VH: [] }} />);
    expect(screen.getByText(/no pass-by-pass values/i)).toBeTruthy();
  });
});

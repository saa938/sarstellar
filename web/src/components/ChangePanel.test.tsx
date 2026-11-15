import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ChangeArea } from "../types.ts";
import ChangePanel, { type ChangePanelResult } from "./ChangePanel.tsx";

afterEach(cleanup);

function makeArea(over: Partial<ChangeArea> = {}): ChangeArea {
  return {
    id: "test-l-1",
    geometry: { type: "Polygon", coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] },
    agreement: "L",
    class: "forest_loss",
    area_ha: 8,
    confidence: 1,
    confidence_label: "High",
    p_value: 1.4e-8,
    change_date: "2026-09-30",
    evidence: [
      { label: "NISAR HV change", value: -3.6, ci: [-3.9, -3.3], unit: "dB", note: "Branches and trunks are gone." },
      { label: "Scene-wide shift removed", value: 0.11, ci: null, unit: "dB", note: "Relative to unchanged forest." },
    ],
    plain_text: "About 8 ha of forest darkened in NISAR's HV channel.",
    series: {
      dates: ["2026-05-21", "2026-05-27", "2026-09-19", "2026-09-30"],
      HH: [null, null, null, null],
      HV: [-12.5, null, null, -16.1],
      VV: [null, null, null, null],
      VH: [null, -12.0, -12.5, null],
    },
    ...over,
  };
}

function makeResult(over: Partial<ChangePanelResult> = {}): ChangePanelResult {
  return { fixture: false, people: { svi_tracts: [] }, exports: { geotiff: null, csv: null, notebook: null }, ...over };
}

describe("ChangePanel", () => {
  it("renders evidence with CI", () => {
    render(<ChangePanel area={makeArea()} result={makeResult()} />);
    const [withCi, withoutCi] = within(screen.getByRole("list", { name: "Evidence" })).getAllByRole("listitem");
    expect(withCi.textContent).toContain("NISAR HV change");
    expect(withCi.textContent).toContain("−3.6 dB");
    expect(withCi.textContent).toContain("95% CI −3.9 to −3.3 dB");
    expect(withCi.textContent).toContain("Branches and trunks are gone.");
    expect(withoutCi.textContent).toContain("+0.11 dB");
    expect(withoutCi.textContent).not.toContain("CI");
  });

  it("export buttons disabled when null", () => {
    const { rerender } = render(<ChangePanel area={makeArea()} result={makeResult()} />);
    for (const name of ["GeoTIFF", "CSV", "Notebook"]) {
      expect((screen.getByRole("button", { name }) as HTMLButtonElement).disabled).toBe(true);
    }
    const url = "https://api.example/exports/j1/change.tif";
    rerender(<ChangePanel area={makeArea()} result={makeResult({ exports: { geotiff: url, csv: null, notebook: null } })} />);
    expect(screen.getByRole("link", { name: "GeoTIFF" }).getAttribute("href")).toBe(url);
    expect(screen.queryByRole("button", { name: "GeoTIFF" })).toBeNull();
    expect((screen.getByRole("button", { name: "CSV" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows class, agreement and the confidence label, never the raw score", () => {
    const { container } = render(<ChangePanel area={makeArea({ confidence: 0.96 })} result={makeResult()} />);
    expect(screen.getByRole("heading", { name: "Forest loss" })).toBeTruthy();
    expect(screen.getByText("Only NISAR saw this")).toBeTruthy();
    const conf = container.querySelector(".cp-conf")!;
    expect(conf.textContent).toContain("High");
    expect(conf.textContent).toContain("p < 0.001");
    expect(conf.textContent).toContain("8 ha");
    expect(container.textContent).not.toMatch(/96|0\.96/);
    expect(screen.getByText(/About 8 ha of forest darkened/)).toBeTruthy();
  });

  it("tags example data", () => {
    const { rerender } = render(<ChangePanel area={makeArea()} result={makeResult({ fixture: true })} />);
    expect(screen.getByText("Example data")).toBeTruthy();
    rerender(<ChangePanel area={makeArea()} result={makeResult({ fixture: false })} />);
    expect(screen.queryByText("Example data")).toBeNull();
  });

  it("lists census tracts, most vulnerable first", () => {
    const tract = (geoid: string, rpl_themes: number) => ({ geoid, rpl_themes, name: `Census Tract ${geoid}` });
    const svi_tracts = [tract("1", 0.4717), tract("2", 0.775), tract("3", 0.5731), tract("4", 0.3001), tract("5", -999)];
    render(<ChangePanel area={makeArea()} result={makeResult({ people: { svi_tracts } })} />);
    const rows = within(screen.getByRole("list", { name: "Census tracts" })).getAllByRole("listitem");
    expect(rows.map((r) => r.textContent)).toEqual([
      "Census Tract 278th percentile",
      "Census Tract 357th percentile",
      "Census Tract 147th percentile",
    ]);
    expect(screen.getByText("+1 more tract in this box")).toBeTruthy();
  });

  it("hides the people block when there are no tracts", () => {
    render(<ChangePanel area={makeArea()} result={makeResult()} />);
    expect(screen.queryByText("Who lives here")).toBeNull();
  });
});

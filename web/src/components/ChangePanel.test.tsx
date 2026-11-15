import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChangeArea } from "../types.ts";
import ChangePanel, { ResultExports, type ChangePanelResult } from "./ChangePanel.tsx";

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
    const [withCi, withoutCi] = within(screen.getByRole("list", { name: "Measurements" })).getAllByRole("listitem");
    expect(withCi.textContent).toContain("NISAR HV change");
    expect(withCi.textContent).toContain("−3.6 dB");
    expect(withCi.textContent).toContain("95% CI −3.9 to −3.3 dB");
    expect(withCi.textContent).toContain("Branches and trunks are gone.");
    expect(withoutCi.textContent).toContain("+0.11 dB");
    expect(withoutCi.textContent).not.toContain("CI");
  });

  it("keeps unavailable exports compact and disables missing files when others exist", () => {
    const { rerender } = render(<ChangePanel area={makeArea()} result={makeResult()} />);
    expect(screen.getByText("Exports unavailable for this result.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "GeoTIFF" })).toBeNull();
    const url = "https://api.example/exports/j1/change.tif";
    rerender(<ChangePanel area={makeArea()} result={makeResult({ exports: { geotiff: url, csv: null, notebook: null } })} />);
    expect(screen.getByRole("link", { name: "GeoTIFF" }).getAttribute("href")).toBe(url);
    expect(screen.queryByRole("button", { name: "GeoTIFF" })).toBeNull();
    expect((screen.getByRole("button", { name: "CSV" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows class, agreement and the confidence label, never the raw score", () => {
    const { container } = render(<ChangePanel area={makeArea({ confidence: 0.96 })} result={makeResult()} />);
    expect(screen.getByRole("heading", { name: "Forest loss" })).toBeTruthy();
    expect(screen.getByText("NISAR only")).toBeTruthy();
    expect(screen.getByText("Classification (rule-based)")).toBeTruthy();
    expect(screen.getByText(/Provisional class hypothesis/)).toBeTruthy();
    const conf = container.querySelector(".cp-conf")!;
    expect(conf.textContent).toContain("High");
    expect(conf.textContent).toContain("p < 0.001");
    expect(conf.textContent).toContain("8 ha");
    expect(container.textContent).not.toMatch(/96|0\.96/);
    expect(screen.getByText(/About 8 ha of forest darkened/)).toBeTruthy();
  });

  it("tags example data", () => {
    const { rerender } = render(<ChangePanel area={makeArea()} result={makeResult({ fixture: true })} />);
    expect(screen.getByText("Test fixture")).toBeTruthy();
    rerender(<ChangePanel area={makeArea()} result={makeResult({ fixture: false })} />);
    expect(screen.queryByText("Test fixture")).toBeNull();
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
    expect(screen.getByText("1 additional tract in the AOI")).toBeTruthy();
  });

  it("hides the people block when there are no tracts", () => {
    render(<ChangePanel area={makeArea()} result={makeResult()} />);
    expect(screen.queryByText("Context: CDC SVI 2022")).toBeNull();
  });

  it("puts dataset exports and measurements before interpretation", () => {
    render(<ChangePanel area={makeArea()} result={makeResult({
      exports: { geotiff: "https://data.example/change.tif", csv: null, notebook: null },
    })} />);
    const exports = screen.getByRole("region", { name: "Exports" });
    const measurements = screen.getByRole("region", { name: "Measurements" });
    const interpretation = screen.getByRole("region", { name: "Interpretation" });
    expect(exports.compareDocumentPosition(measurements) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(measurements.compareDocumentPosition(interpretation) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText("First flagged acquisition: Sep 30, 2026 (UTC).")).toBeTruthy();
  });

  it("returns to the area list through a named action", () => {
    const onClose = vi.fn();
    render(<ChangePanel area={makeArea()} result={makeResult()} onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: "Back to areas" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("exports dataset files without requiring a selected area", () => {
    render(<ResultExports files={{ geotiff: "https://data.example/change.tif", csv: null, notebook: null }} />);
    expect(screen.getByRole("link", { name: "GeoTIFF" }).getAttribute("href")).toBe("https://data.example/change.tif");
    expect((screen.getByRole("button", { name: "CSV" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

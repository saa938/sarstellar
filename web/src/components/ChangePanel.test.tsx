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
    expect(screen.getByRole("heading", { name: "Change detected" })).toBeTruthy();
    expect(screen.getByText("Possible forest loss")).toBeTruthy();
    expect(screen.getByText("NISAR majority")).toBeTruthy();
    expect(screen.getByText("Provisional rule-based interpretation.")).toBeTruthy();
    const technical = screen.getByText("Technical statistics").closest("details")!;
    expect(technical.open).toBe(false);
    fireEvent.click(screen.getByText("Technical statistics"));
    const statistics = screen.getByRole("region", { name: "Detector statistics" });
    expect(statistics.textContent).toContain("High");
    expect(statistics.textContent).toContain("p < 0.001");
    expect(statistics.textContent).toContain("8 ha");
    expect(statistics.textContent).toContain("not a class probability");
    expect(container.querySelector(".cp-bar")).toBeNull();
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
    const technical = screen.getByText("Technical statistics");
    const next = screen.getByRole("region", { name: "What to check next?" });
    expect(next.compareDocumentPosition(exports) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(exports.compareDocumentPosition(technical) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(exports.compareDocumentPosition(measurements) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(measurements.compareDocumentPosition(interpretation) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText(/First flagged acquisition: Sep 30, 2026 \(UTC\)/)).toBeTruthy();
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

  it("answers the four observation questions before technical statistics", () => {
    render(<ChangePanel area={makeArea()} result={makeResult()} />);
    const observed = screen.getByRole("region", { name: "What changed?" });
    const when = screen.getByRole("region", { name: "When?" });
    const why = screen.getByRole("region", { name: "Why this hypothesis?" });
    const next = screen.getByRole("region", { name: "What to check next?" });
    const statistics = screen.getByText("Technical statistics");
    expect(observed.textContent).toContain("8 ha");
    expect(observed.textContent).toContain("does not establish a physical cause");
    expect(when.textContent).toContain("First flagged acquisition: Sep 30, 2026 (UTC)");
    expect(when.textContent).toContain("no event date is established");
    expect(why.textContent).toContain("Possible forest loss");
    expect(next.textContent).toContain("independent pre/post optical imagery");
    expect(next.compareDocumentPosition(statistics) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("does not invent an event date when no onset acquisition is identified", () => {
    render(<ChangePanel area={makeArea({ change_date: null })} result={makeResult()} />);
    const when = screen.getByRole("region", { name: "When?" });
    expect(when.textContent).toContain("No onset acquisition identified");
    expect(when.textContent).toContain("no event date is established");
    expect(when.textContent).not.toContain("First flagged acquisition:");
  });

  it("shows both available sensor windows because majority labels do not imply exclusive detection", () => {
    render(<ChangePanel area={makeArea({ agreement: "C" })} result={makeResult({
      nisar: { track: 71, direction: "D", dates: ["2026-07-13", "2026-09-11"] },
      s1: { track: 166, dates: ["2026-07-11", "2026-09-09"] },
    })} />);
    const when = screen.getByRole("region", { name: "When?" });
    const windows = within(when).getByText("Acquisition windows");
    expect(windows.closest("details")!.open).toBe(false);
    fireEvent.click(windows);
    expect(when.textContent).toContain("Sentinel-1 window: Jul 11 – Sep 9, 2026");
    expect(when.textContent).toContain("NISAR window: Jul 13 – Sep 11, 2026");
  });

  it("qualifies saved rule wording in support and measurements and links internal sources to Methods", () => {
    const rule = Object.freeze({ label: "Rule fired", value: "HV fell 3 dB or more (canopy removed)",
      ci: null, unit: "", note: "research table (docs/research/science.md, literature values)" });
    const area = makeArea({ evidence: [rule], plain_text: "Rule: double bounce off standing water." });
    const original = JSON.stringify(area);
    const { container } = render(<ChangePanel area={area} result={makeResult()} />);
    expect(screen.getAllByText("HV fell 3 dB or more (consistent with canopy loss)")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "Methods and rule criteria" }).getAttribute("href")).toBe("#/about");
    expect(container.textContent).toContain("possible double-bounce response");
    expect(container.textContent).not.toContain("(canopy removed)");
    expect(container.textContent).not.toContain("docs/research/science.md");
    expect(JSON.stringify(area)).toBe(original);
  });

  it("keeps unresolved classifications unresolved and supplies verification steps", () => {
    render(<ChangePanel area={makeArea({ class: "uncertain" })} result={makeResult()} />);
    const why = screen.getByRole("region", { name: "Why this hypothesis?" });
    expect(why.textContent).toContain("Cause unresolved");
    expect(why.textContent).not.toContain("Possible forest loss");
    const next = screen.getByRole("list", { name: "Verification steps" });
    expect(within(next).getAllByRole("listitem")).toHaveLength(2);
    expect(next.textContent).toContain("independent pre/post imagery");
  });
});

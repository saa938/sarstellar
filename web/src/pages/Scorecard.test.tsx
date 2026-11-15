import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// MapLibre needs WebGL, which happy-dom lacks; the site map only needs to mount without throwing.
vi.mock("maplibre-gl", () => {
  class Evented {
    on() {
      return this;
    }
  }
  class Map extends Evented {
    addControl() {
      return this;
    }
    addSource() {}
    addLayer() {}
    getCanvas() {
      return { style: {} };
    }
    remove() {}
  }
  class NavigationControl {}
  class Popup {
    setLngLat() {
      return this;
    }
    setText() {
      return this;
    }
    addTo() {
      return this;
    }
    remove() {
      return this;
    }
  }
  return { Map, NavigationControl, Popup, setWorkerUrl: () => {} };
});

import ScorecardPage from "./Scorecard.tsx";
import { sampleScorecard } from "./scorecardSample.ts";
import actualReport from "../../public/scorecard.json";
import type { Scorecard } from "../types.ts";

afterEach(cleanup);

describe("Scorecard page", () => {
  it("starts with pooled results and lets readers inspect a land-cover stratum", () => {
    const report = actualReport as unknown as Scorecard;
    render(<ScorecardPage data={report} />);
    expect(screen.getAllByRole("img", { name: /AUPRC/ })).toHaveLength(report.classes.filter((row) => row.landcover === "all").length);
    fireEvent.change(screen.getByRole("combobox", { name: "Land cover" }), { target: { value: "forest" } });
    expect(screen.getAllByRole("img", { name: /AUPRC/ })).toHaveLength(report.classes.filter((row) => row.landcover === "forest").length);
  });

  it("renders the real paired report with actual counts, Bonferroni and reference caveats", () => {
    const report = actualReport as unknown as Scorecard;
    render(<ScorecardPage data={report} />);
    const text = document.body.textContent ?? "";
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain(
      `On ${report.n_holdout_sites} held-out sites in ${report.holdout_states.length} states`,
    );
    expect(text).toContain(`${report.n_sites} eligible sites from ${report.n_attempted} attempted`);
    expect(text).toContain(`${report.failed_sites!.length} failed and ${report.excluded_sites!.length} were excluded`);
    expect(text).toContain("only 3 held-out flood sites");
    expect(text).toContain("Bonferroni fusion");
    expect(text).toContain("DSWx-S1 itself uses Sentinel-1");
    expect(text).toContain("CDL marks cultivated land");
    expect(text).toContain("at most 1.5%");
    expect(screen.getByRole("heading", { name: "Learned fusion with matched training" })).toBeTruthy();
    expect(text).toContain(report.notes);
    expect(text).not.toContain("300+");
  });

  it("scorecard renders from sample json", () => {
    render(<ScorecardPage data={sampleScorecard()} />);

    // Headline = the fusion result.
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "On 4 held-out sites in 2 states, combining NISAR and Sentinel-1 improved forest loss detection by +0.12 AUPRC (95% CI 0.04 to 0.20) over NISAR (L-band) alone.",
    );
    // Per-class detector bars with CIs.
    expect(screen.getByRole("img", { name: "NISAR (L-band): AUPRC 0.61, 95% CI 0.52 to 0.70" })).toBeTruthy();
    expect(screen.getByRole("img", { name: "Sentinel-1 (C-band): AUPRC 0.47, 95% CI 0.36 to 0.58" })).toBeTruthy();
    expect(screen.getAllByRole("img", { name: /AUPRC/ })).toHaveLength(8);
    // Equal-recall ratios, both directions (Sentinel-1 winning must stay visible).
    expect(screen.getByText("3.1×")).toBeTruthy();
    expect(screen.getByText("0.24×")).toBeTruthy();
    // Stable false-alarm rates.
    expect(screen.getByText("1.2%")).toBeTruthy();
    // Site map legend with train/holdout split.
    expect(screen.getByText("4 training sites", { exact: true })).toBeTruthy();
    expect(screen.getByText(/4 held-out sites in GA, OR/)).toBeTruthy();
    // Reading guide; no rules-vs-model table while `model` is null.
    expect(screen.getByText("How to read this")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: /rules vs learned model/i })).toBeNull();
  });

  it("states the honest null when fusion did not help", () => {
    const sc = sampleScorecard({
      fusion: [{ class: "forest_loss", best_single: "L", fused: "fused_fisher", metric: "auprc", delta: 0.01, ci_low: -0.03, ci_high: 0.05, p_gt0: 0.6 }],
    });
    render(<ScorecardPage data={sc} />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("did not measurably beat the better single radar");
  });

  it("shows the rules-vs-model table only when a model is present", () => {
    const model = {
      per_class: [{ class: "forest_loss", rules_f1: 0.48, model_f1: 0.55, winner: "model" }],
      macro_f1_rules: 0.41,
      macro_f1_model: 0.45,
    };
    render(<ScorecardPage data={sampleScorecard({ model })} />);
    expect(screen.getByRole("heading", { name: /rules vs learned model/i })).toBeTruthy();
    expect(screen.getByText("0.55")).toBeTruthy();
  });

  it("stays hidden until scorecard.json exists", async () => {
    const { container } = render(<ScorecardPage data={null} />);
    expect(container.innerHTML).toBe("");
    cleanup();

    const fetchMock = vi.fn(async () => new Response("not found", { status: 404 }));
    vi.stubGlobal("fetch", fetchMock);
    const missing = render(<ScorecardPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(missing.container.innerHTML).toBe("");
    cleanup();

    vi.stubGlobal("fetch", vi.fn(async () => Response.json(sampleScorecard())));
    render(<ScorecardPage />);
    expect((await screen.findByRole("heading", { level: 1 })).textContent).toContain("held-out sites");
  });
});

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import About from "./About.tsx";

afterEach(cleanup);

describe("About page", () => {
  it("covers data, method, limits, AI use, references and license", () => {
    render(<About />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Methods");
    for (const name of ["Data", "Processing", "Validation", "Limits", "AI use", "References", "License"]) {
      expect(screen.getByRole("heading", { name })).toBeTruthy();
    }
    const text = document.body.textContent ?? "";
    expect(text).toContain("NISAR L2 GCOV");
    expect(text).toContain("OPERA RTC-S1");
    expect(text).toContain("DIST-ALERT-HLS");
    expect(text).toContain("Open-Meteo");
    expect(text).toContain("Apache-2.0");
    expect(screen.getByRole("link", { name: "github.com/saa938/sarstellar" })).toBeTruthy();
  });

  it("explains the revised Kaiser comparison, reference limitations and NISAR gap", () => {
    render(<About />);
    const text = document.body.textContent ?? "";
    expect(text).toMatch(/Kaiser Canyon[^.]*Sentinel-1/);
    expect(text).toContain("the full pipeline changed that comparison");
    expect(text).toContain("not an independent flood check");
    expect(text).toContain("does not isolate wavelength");
    expect(text).not.toContain("300+");
    expect(text).not.toContain("Sentinel-1 saw the burn far more clearly");
    expect(text).toContain("Jul 27 to Aug 10, 2026");
  });
});

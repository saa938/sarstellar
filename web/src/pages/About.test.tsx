import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import About from "./About.tsx";

afterEach(cleanup);

describe("About page", () => {
  it("covers data, method, limits, AI use, references and license", () => {
    render(<About />);
    for (const name of ["Data we use", "Method", "Limits", "AI use", "References", "License"]) {
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

  it("keeps the Kaiser Canyon result (Sentinel-1 wins) and the NISAR gap visible", () => {
    render(<About />);
    const text = document.body.textContent ?? "";
    expect(text).toMatch(/Kaiser Canyon[^.]*Sentinel-1/);
    expect(text).toContain("Jul 27 to Aug 10, 2026");
  });
});

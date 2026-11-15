import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import kaiser from "../../public/stories/kaiser.json";
import type { Result } from "../types.ts";
import CaseStudy from "./CaseStudy.tsx";

afterEach(cleanup);

it("links an actual saved disagreement to its measurements and corroboration limits", () => {
  const onSelectArea = vi.fn();
  render(<CaseStudy storyId="kaiser" result={kaiser as Result} onSelectArea={onSelectArea} />);
  fireEvent.click(screen.getByText("Investigation: Kaiser Canyon"));
  expect(screen.getByText("−2.84 dB")).toBeTruthy();
  expect(screen.getByText("−2.13 dB")).toBeTruthy();
  expect(screen.getByText(/does not imply zero Sentinel-1 detections/)).toBeTruthy();
  expect(screen.getByText(/not a separate validation test/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Inspect area a1" }));
  expect(onSelectArea).toHaveBeenCalledWith("a1");
  expect(screen.getByRole("link", { name: "Download saved areas (CSV)" }).getAttribute("href")).toBe("/stories/kaiser/areas.csv");
});

it("does not invent corroboration when the source result lacks it", () => {
  const result = structuredClone(kaiser) as Result;
  result.areas[0].evidence = result.areas[0].evidence.filter((ev) => ev.label !== "Inside fire perimeter");
  render(<CaseStudy storyId="kaiser" result={result} />);
  fireEvent.click(screen.getByText("Investigation: Kaiser Canyon"));
  expect(screen.getByText(/has no fire-perimeter corroboration/)).toBeTruthy();
});

it("shows no case-specific claims for another story or live result", () => {
  const { container } = render(<CaseStudy storyId={null} result={kaiser as Result} />);
  expect(container.textContent).toBe("");
});

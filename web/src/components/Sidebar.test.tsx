import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { sampleResult } from "../test/sample.ts";
import type { SidebarProps } from "./Sidebar.tsx";
import { Sidebar } from "./Sidebar.tsx";

afterEach(cleanup);

function props(overrides: Partial<SidebarProps> = {}): SidebarProps {
  return {
    stories: [{ id: "kaiser", title: "Kaiser Canyon Fire", place: "Washington",
      dates: ["2026-07-13", "2026-09-11"], summary: "", fixture: false }],
    activeStoryId: "kaiser", onSelectStory: vi.fn(), result: sampleResult(), hidden: new Set(),
    onToggleAgreement: vi.fn(), ...overrides,
  };
}

it("foregrounds example selection and each sensor's actual acquisition metadata", () => {
  const p = props();
  render(<Sidebar {...p} />);
  expect(screen.getByText(/^Examples/)).toBeTruthy();
  const acquisition = screen.getByRole("group", { name: "Acquisition metadata" });
  expect(acquisition.textContent).toContain("3 · track 71 · descending");
  expect(acquisition.textContent).toContain("2 · track 166");
  expect(acquisition.textContent).toContain("Jul 13 – Sep 11, 2026");
  expect(acquisition.textContent).toContain("Jul 11 – Sep 9, 2026");
  fireEvent.click(screen.getByRole("button", { name: /Kaiser Canyon Fire/ }));
  expect(p.onSelectStory).toHaveBeenCalledWith("kaiser");
});

it("exposes the four source coordinates with a declared coordinate system", () => {
  const r = sampleResult();
  render(<Sidebar {...props({ result: r })} />);
  fireEvent.click(screen.getByText("Coordinates"));
  const coordinates = screen.getByRole("group", { name: "AOI coordinates" });
  for (const value of r.bbox) expect(coordinates.textContent).toContain(String(value));
  expect(screen.getByText(/WGS 84/)).toBeTruthy();
});

it("uses a percentage control while passing normalized opacity to the map", () => {
  const onOpacityChange = vi.fn();
  render(<Sidebar {...props({ layerOpacity: 0.75, onOpacityChange })} />);
  const range = screen.getByRole("slider", { name: "Area opacity" }) as HTMLInputElement;
  expect(range.value).toBe("75");
  fireEvent.change(range, { target: { value: "35" } });
  expect(onOpacityChange).toHaveBeenCalledWith(0.35);
});

it("disables irrelevant area controls in comparison views", () => {
  render(<Sidebar {...props({ layerControlsEnabled: false, onOpacityChange: vi.fn() })} />);
  const sidebar = screen.getByRole("complementary", { name: "Analysis workspace" });
  const legend = within(sidebar).getByRole("button", { name: /NISAR only:/ }) as HTMLButtonElement;
  expect(legend.disabled).toBe(true);
  expect((screen.getByRole("slider", { name: "Area opacity" }) as HTMLInputElement).disabled).toBe(true);
  expect(screen.getByText("Area controls apply to the Detected areas view.")).toBeTruthy();
});

it("reports unavailable Sentinel-1 metadata instead of a zero acquisition claim", () => {
  render(<Sidebar {...props({ result: sampleResult({ s1: null }) })} />);
  expect(within(screen.getByRole("group", { name: "Acquisition metadata" })).getAllByText("Unavailable")).toHaveLength(2);
});

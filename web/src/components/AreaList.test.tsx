import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { area } from "../test/sample.ts";
import type { Agreement } from "../types.ts";
import { AreaList } from "./AreaList.tsx";

afterEach(cleanup);

const many = Array.from({ length: 230 }, (_, i) => area(`a${i}`, i % 3 === 0 ? "C" : "L", i + 1));

describe("AreaList", () => {
  it("lists the 25 largest areas and leaves the rest to the map", () => {
    render(<AreaList areas={many} hidden={new Set()} onSelect={() => {}} />);
    const items = screen.getAllByRole("button");
    expect(items).toHaveLength(25);
    expect(items[0].textContent).toContain("230 ha");
    expect(screen.getByText("205 additional matching areas on the map.")).toBeTruthy();
  });

  it("skips agreements hidden in the legend", () => {
    render(<AreaList areas={many} hidden={new Set<Agreement>(["L"])} onSelect={() => {}} />);
    const items = screen.getAllByRole("button");
    expect(items.every((b) => b.textContent?.includes("Sentinel-1 only"))).toBe(true);
    // 77 areas are C; 25 listed.
    expect(screen.getByText("52 additional matching areas on the map.")).toBeTruthy();
  });

  it("selects an area when clicked", () => {
    const onSelect = vi.fn<(id: string) => void>();
    render(<AreaList areas={[area("x", "both", 5)]} hidden={new Set()} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: /Burned area/ }));
    expect(onSelect).toHaveBeenCalledWith("x");
    expect(screen.queryByText(/additional matching areas/)).toBeNull();
  });

  it("says so when no areas passed the tests", () => {
    render(<AreaList areas={[]} hidden={new Set()} onSelect={() => {}} />);
    expect(screen.getByText("No areas meet the detection criteria.")).toBeTruthy();
  });

  it("finds classes beyond the initial largest 25 and caps the filtered result", () => {
    const forests = Array.from({ length: 35 }, (_, i) =>
      ({ ...area(`forest-${i}`, "L", i + 1), class: "forest_loss" as const }));
    const onSelect = vi.fn();
    render(<AreaList areas={[...many, ...forests]} hidden={new Set()} onSelect={onSelect} />);
    expect(screen.queryByRole("button", { name: /Forest loss/ })).toBeNull();
    fireEvent.change(screen.getByLabelText("Class"), { target: { value: "forest_loss" } });
    const items = screen.getAllByRole("button");
    expect(items).toHaveLength(25);
    expect(items[0].textContent).toContain("35 ha");
    expect(screen.getByRole("status").textContent).toContain("35 of 265 areas");
    expect(screen.getByText("10 additional matching areas on the map.")).toBeTruthy();
    fireEvent.click(items[0]);
    expect(onSelect).toHaveBeenCalledWith("forest-34");
  });

  it("combines class and layer filters and recovers if the selected class disappears", () => {
    const forests = [{ ...area("forest", "L", 5), class: "forest_loss" as const }];
    const view = render(<AreaList areas={[...many, ...forests]} hidden={new Set()} onSelect={() => {}} />);
    fireEvent.change(screen.getByLabelText("Class"), { target: { value: "forest_loss" } });
    view.rerender(<AreaList areas={[...many, ...forests]} hidden={new Set<Agreement>(["L"])} onSelect={() => {}} />);
    expect(screen.getByRole("status").textContent).toContain("0 of 231 areas");
    expect(screen.getByText("No areas match the class and layer filters.")).toBeTruthy();
    view.rerender(<AreaList areas={many} hidden={new Set()} onSelect={() => {}} />);
    expect((screen.getByLabelText("Class") as HTMLSelectElement).value).toBe("all");
    expect(screen.getAllByRole("button")).toHaveLength(25);
  });
});

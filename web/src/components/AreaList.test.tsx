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
    expect(screen.getByText("205 smaller areas are on the map only.")).toBeTruthy();
  });

  it("skips agreements hidden in the legend", () => {
    render(<AreaList areas={many} hidden={new Set<Agreement>(["L"])} onSelect={() => {}} />);
    const items = screen.getAllByRole("button");
    expect(items.every((b) => b.textContent?.includes("Only Sentinel-1"))).toBe(true);
    // 77 areas are C; 25 listed.
    expect(screen.getByText("52 smaller areas are on the map only.")).toBeTruthy();
  });

  it("selects an area when clicked", () => {
    const onSelect = vi.fn<(id: string) => void>();
    render(<AreaList areas={[area("x", "both", 5)]} hidden={new Set()} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: /Burned area/ }));
    expect(onSelect).toHaveBeenCalledWith("x");
    expect(screen.queryByText(/on the map only/)).toBeNull();
  });

  it("says so when no areas passed the tests", () => {
    render(<AreaList areas={[]} hidden={new Set()} onSelect={() => {}} />);
    expect(screen.getByText("No change areas passed the tests in this box.")).toBeTruthy();
  });
});

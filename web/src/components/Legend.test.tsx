import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { area } from "../test/sample.ts";
import type { Agreement } from "../types.ts";
import { Legend } from "./Legend.tsx";

afterEach(cleanup);

const areas = [area("a", "L", 6000.4), area("b", "L", 240), area("c", "both", 410), area("d", "C", 380), area("e", "C", 1200)];

function row(name: string): HTMLElement {
  return screen.getByRole("button", { name: new RegExp(name) });
}

describe("Legend", () => {
  it("hectare sums match areas", () => {
    render(<Legend areas={areas} hidden={new Set()} onToggle={() => {}} />);
    expect(row("Only NISAR saw it").textContent).toContain("6,240 ha");
    expect(row("Both satellites saw it").textContent).toContain("410 ha");
    expect(row("Only Sentinel-1 saw it").textContent).toContain("1,580 ha");
  });

  it("legend toggle hides agreement", () => {
    const onToggle = vi.fn<(a: Agreement) => void>();
    const { rerender } = render(<Legend areas={areas} hidden={new Set()} onToggle={onToggle} />);
    expect(row("Only NISAR saw it").getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(row("Only NISAR saw it"));
    expect(onToggle).toHaveBeenCalledWith("L");

    rerender(<Legend areas={areas} hidden={new Set<Agreement>(["L"])} onToggle={onToggle} />);
    expect(row("Only NISAR saw it").getAttribute("aria-pressed")).toBe("false");
    expect(row("Only NISAR saw it").className).toContain("off");
    expect(row("Both satellites saw it").getAttribute("aria-pressed")).toBe("true");
  });
});

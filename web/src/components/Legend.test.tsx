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
    expect(row("NISAR majority").textContent).toContain("6,240 ha");
    expect(row("Both / mixed").textContent).toContain("410 ha");
    expect(row("Sentinel-1 majority").textContent).toContain("1,580 ha");
    expect(screen.getByText(/Area labels summarize block majorities/).textContent).toContain("the other radar may flag some blocks");
    expect(screen.getByText(/Both \/ mixed means/).textContent).toContain("both or neither radar flagged a majority");
  });

  it("legend toggle hides agreement", () => {
    const onToggle = vi.fn<(a: Agreement) => void>();
    const { rerender } = render(<Legend areas={areas} hidden={new Set()} onToggle={onToggle} />);
    expect(row("NISAR majority").getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(row("NISAR majority"));
    expect(onToggle).toHaveBeenCalledWith("L");

    rerender(<Legend areas={areas} hidden={new Set<Agreement>(["L"])} onToggle={onToggle} />);
    expect(row("NISAR majority").getAttribute("aria-pressed")).toBe("false");
    expect(row("NISAR majority").className).toContain("off");
    expect(row("Both / mixed").getAttribute("aria-pressed")).toBe("true");
  });

  it("disables layer controls when they do not apply to the current view", () => {
    const onToggle = vi.fn();
    render(<Legend areas={areas} hidden={new Set()} onToggle={onToggle} disabled />);
    const button = row("NISAR majority") as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.click(button);
    expect(onToggle).not.toHaveBeenCalled();
  });
});

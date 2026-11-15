import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import Timeline, { type DatePair } from "./Timeline.tsx";

afterEach(cleanup);

const DATES = ["2026-07-13", "2026-07-25", "2026-08-18", "2026-08-30", "2026-09-11"];

const tick = (name: RegExp) => screen.getByRole("button", { name });
const leftPct = (el: HTMLElement) => parseFloat(el.style.left);

function Harness({ onChange }: { onChange: (pair: DatePair) => void }) {
  const [value, setValue] = useState<DatePair | null>(null);
  return (
    <Timeline
      dates={DATES}
      value={value}
      onChange={(pair) => {
        setValue(pair);
        onChange(pair);
      }}
    />
  );
}

describe("Timeline", () => {
  it("gap drawn between 2026-07-27 and 2026-08-10", () => {
    render(<Timeline dates={DATES} value={null} onChange={() => {}} />);
    const gap = screen.getByRole("img", { name: /NISAR acquisition gap/i });
    expect(gap.getAttribute("aria-label")).toContain("Jul 27");
    expect(gap.getAttribute("aria-label")).toContain("Aug 10");

    // The striped band sits between the Jul 25 and Aug 18 passes, at the gap's true position in time.
    const a = leftPct(tick(/Jul 25, 2026/));
    const b = leftPct(tick(/Aug 18, 2026/));
    const start = leftPct(gap);
    const end = start + parseFloat(gap.style.width);
    const frac = (iso: string) => (Date.parse(iso) - Date.parse("2026-07-25")) / (Date.parse("2026-08-18") - Date.parse("2026-07-25"));
    expect((start - a) / (b - a)).toBeCloseTo(frac("2026-07-27T22:03:00Z"), 3);
    expect((end - a) / (b - a)).toBeCloseTo(frac("2026-08-10T00:55:00Z"), 3);
  });

  it("draws no gap when the passes don't span it", () => {
    render(<Timeline dates={["2026-08-26", "2026-09-07"]} value={null} onChange={() => {}} />);
    expect(screen.queryByRole("img", { name: /NISAR acquisition gap/i })).toBeNull();
  });

  it("defaults to comparing the first and last pass", () => {
    render(<Timeline dates={DATES} value={null} onChange={() => {}} />);
    const pressed = screen.getAllByRole("button").filter((b) => b.getAttribute("aria-pressed") === "true");
    expect(pressed.map((b) => b.getAttribute("aria-label"))).toEqual([
      expect.stringContaining("Jul 13, 2026"),
      expect.stringContaining("Sep 11, 2026"),
    ]);
  });

  it("selecting two dates sets the dates for the next job", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    fireEvent.click(tick(/Jul 25, 2026/));
    expect(onChange).toHaveBeenLastCalledWith(["2026-07-25", "2026-09-11"]);
    fireEvent.click(tick(/Aug 30, 2026/));
    expect(onChange).toHaveBeenLastCalledWith(["2026-07-25", "2026-08-30"]);
    expect(tick(/Aug 30, 2026/).getAttribute("aria-pressed")).toBe("true");
    expect(tick(/Sep 11, 2026/).getAttribute("aria-pressed")).toBe("false");
  });

  it("clicking an already selected pass changes nothing", () => {
    const onChange = vi.fn();
    render(<Timeline dates={DATES} value={["2026-07-13", "2026-09-11"]} onChange={onChange} />);
    fireEvent.click(tick(/Sep 11, 2026/));
    expect(onChange).not.toHaveBeenCalled();
  });

  it("labels date selection for the next analysis rather than claiming a rerun", () => {
    render(<Timeline dates={DATES} value={null} onChange={() => {}} />);
    expect(screen.getByText(/Next analysis:/)).toBeTruthy();
    expect(tick(/Jul 13, 2026/).getAttribute("title")).toContain("UTC");
  });
});

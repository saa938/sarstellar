// Three-color legend: one toggle per agreement, with the hectares each covers in the current result.
import { AGREEMENTS, AGREEMENT_LABELS, hectareSums } from "../areas.ts";
import { AGREEMENT_COLORS, type Agreement, type ChangeArea } from "../types.ts";
import { formatHa } from "./changeFormat.ts";

export interface LegendProps {
  areas: readonly ChangeArea[];
  /** Agreements currently hidden on the map. */
  hidden: ReadonlySet<Agreement>;
  onToggle: (agreement: Agreement) => void;
}

export function Legend({ areas, hidden, onToggle }: LegendProps) {
  const sums = hectareSums(areas);
  const shortLabels: Record<Agreement, string> = { L: "NISAR only", both: "Both radars", C: "Sentinel-1 only" };
  return (
    <div className="legend">
      {AGREEMENTS.map((k) => {
        const shown = !hidden.has(k);
        return (
          <button key={k} type="button" className={shown ? "row" : "row off"}
            aria-label={`${AGREEMENT_LABELS[k]} ${formatHa(sums[k])} ha`}
            aria-pressed={shown} onClick={() => onToggle(k)}>
            <span className="sw" style={{ background: AGREEMENT_COLORS[k] }} aria-hidden="true" />
            <span className="legend-label">{shortLabels[k]}</span>
            <span className="ha">{formatHa(sums[k])} ha</span>
            <span className="legend-state" aria-hidden="true">{shown ? "✓" : ""}</span>
          </button>
        );
      })}
    </div>
  );
}

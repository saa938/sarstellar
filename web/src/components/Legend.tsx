// Three-color legend: one toggle per agreement, with the hectares each covers in the current result.
import { AGREEMENTS, hectareSums } from "../areas.ts";
import { AGREEMENT_COLORS, type Agreement, type ChangeArea } from "../types.ts";
import { formatHa } from "./changeFormat.ts";

export interface LegendProps {
  areas: readonly ChangeArea[];
  /** Agreements currently hidden on the map. */
  hidden: ReadonlySet<Agreement>;
  onToggle: (agreement: Agreement) => void;
  disabled?: boolean;
}

export const DETECTION_LABELS: Record<Agreement, string> = {
  L: "NISAR only", both: "Both sensors", C: "Sentinel-1 only",
};

export function Legend({ areas, hidden, onToggle, disabled = false }: LegendProps) {
  const sums = hectareSums(areas);
  return (
    <div className="legend" role="group" aria-label="Detection layers">
      {AGREEMENTS.map((k) => {
        const shown = !hidden.has(k);
        return (
          <button key={k} type="button" className={shown ? "row" : "row off"}
            aria-label={`${DETECTION_LABELS[k]}: ${formatHa(sums[k])} ha`}
            aria-pressed={shown} disabled={disabled} onClick={() => onToggle(k)}>
            <span className="sw" style={{ background: AGREEMENT_COLORS[k] }} aria-hidden="true" />
            <span className="legend-label">{DETECTION_LABELS[k]}</span>
            <span className="ha">{formatHa(sums[k])} ha</span>
            <span className="legend-state" aria-hidden="true">{shown ? "✓" : ""}</span>
          </button>
        );
      })}
    </div>
  );
}

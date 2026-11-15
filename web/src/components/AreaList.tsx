// "Largest changes": the biggest visible change areas as a clickable list. A live box can return 200+ areas,
// so only AREA_LIST_LIMIT are listed; every area still draws on the map.
import { largestAreas } from "../areas.ts";
import { useId, useState } from "react";
import { AGREEMENT_COLORS, type Agreement, type ChangeArea } from "../types.ts";
import { classTitle, formatHa } from "./changeFormat.ts";
import { DETECTION_LABELS } from "./Legend.tsx";

export interface AreaListProps {
  areas: readonly ChangeArea[];
  /** Agreements hidden in the legend are left out here too. */
  hidden: ReadonlySet<Agreement>;
  onSelect: (id: string) => void;
}

export function AreaList({ areas, hidden, onSelect }: AreaListProps) {
  const selectId = useId();
  const [filter, setFilter] = useState("all");
  const classes = [...new Set(areas.map((a) => a.class))].sort((a, b) => classTitle(a).localeCompare(classTitle(b)));
  const selected = classes.some((cls) => cls === filter) ? filter : "all";
  if (areas.length === 0) return <p className="hint">No areas meet the detection criteria.</p>;
  const visible = areas.filter((a) => !hidden.has(a.agreement) && (selected === "all" || a.class === selected));
  const listed = largestAreas(visible);
  const rest = visible.length - listed.length;
  return (
    <>
      <div className="area-filter">
        <label htmlFor={selectId}>Class</label>
        <select id={selectId} value={selected} onChange={(event) => setFilter(event.target.value)}>
          <option value="all">All classes</option>
          {classes.map((cls) => <option key={cls} value={cls}>{classTitle(cls)}</option>)}
        </select>
      </div>
      <p className="hint" role="status">{visible.length.toLocaleString("en-US")} of {areas.length.toLocaleString("en-US")} areas · largest first</p>
      {visible.length === 0 && <p className="hint">No areas match the class and layer filters.</p>}
      <ul className="area-list">
        {listed.map((a) => (
          <li key={a.id}>
            <button type="button" onClick={() => onSelect(a.id)}>
              <span className="sw" style={{ background: AGREEMENT_COLORS[a.agreement] }} aria-hidden="true" />
              <span className="area-name">
                {classTitle(a.class)}
                <small>{DETECTION_LABELS[a.agreement]} · {a.id}</small>
              </span>
              <span className="ha">{formatHa(a.area_ha)} ha</span>
            </button>
          </li>
        ))}
      </ul>
      {rest > 0 && <p className="hint">{rest.toLocaleString("en-US")} additional matching areas on the map.</p>}
    </>
  );
}

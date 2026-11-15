// "Largest changes": the biggest visible change areas as a clickable list. A live box can return 200+ areas,
// so only AREA_LIST_LIMIT are listed; every area still draws on the map.
import { largestAreas } from "../areas.ts";
import { AGREEMENT_COLORS, type Agreement, type ChangeArea } from "../types.ts";
import { AGREEMENT_TEXT, classTitle, formatHa } from "./changeFormat.ts";

export interface AreaListProps {
  areas: readonly ChangeArea[];
  /** Agreements hidden in the legend are left out here too. */
  hidden: ReadonlySet<Agreement>;
  onSelect: (id: string) => void;
}

export function AreaList({ areas, hidden, onSelect }: AreaListProps) {
  if (areas.length === 0) return <p className="hint">No change areas passed the tests in this box.</p>;
  const visible = areas.filter((a) => !hidden.has(a.agreement));
  const listed = largestAreas(visible);
  const rest = visible.length - listed.length;
  return (
    <>
      <ul className="area-list">
        {listed.map((a) => (
          <li key={a.id}>
            <button type="button" onClick={() => onSelect(a.id)}>
              <span className="sw" style={{ background: AGREEMENT_COLORS[a.agreement] }} aria-hidden="true" />
              <span className="area-name">
                {classTitle(a.class)}
                <small>{AGREEMENT_TEXT[a.agreement]}</small>
              </span>
              <span className="ha">{formatHa(a.area_ha)} ha</span>
            </button>
          </li>
        ))}
      </ul>
      {rest > 0 && <p className="hint">{rest.toLocaleString("en-US")} smaller areas are on the map only.</p>}
    </>
  );
}

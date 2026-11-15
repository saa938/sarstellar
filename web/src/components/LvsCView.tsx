// NISAR and Sentinel-1 change images, with candidate-patch category areas rather than flagged-block totals.
import "maplibre-gl/dist/maplibre-gl.css";
import "./ComparisonViews.css";
import { useEffect, useMemo, useRef, useState } from "react";
import { AGREEMENT_COLORS, type ChangeArea, type Result } from "../types.ts";
import { createRadarMap, formatHa, formatPass, observeMaps, sensorTotals, syncMaps, updateSelectedArea } from "./comparisonmaphelpers.ts";

export interface LvsCViewProps {
  result: Result;
  selectedArea?: ChangeArea | null;
}

export default function LvsCView({ result, selectedArea = null }: LvsCViewProps) {
  const { bbox, overlays, areas } = result;
  const lRef = useRef<HTMLDivElement>(null);
  const cRef = useRef<HTMLDivElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const mapsRef = useRef<ReturnType<typeof createRadarMap>[]>([]);
  const selectedRef = useRef(selectedArea);
  selectedRef.current = selectedArea;
  const [error, setError] = useState<string | null>(null);
  const totals = useMemo(() => sensorTotals(areas), [areas]);

  useEffect(() => {
    if (!lRef.current || !wrapRef.current) return;
    const maps: ReturnType<typeof createRadarMap>[] = [];
    mapsRef.current = maps;
    const syncSelection = () => maps.forEach((map) => updateSelectedArea(map, selectedRef.current));
    let stopSync = () => {};
    let stopResize = () => {};
    const cleanup = () => {
      stopResize();
      stopSync();
      maps.splice(0).forEach((map) => { map.off("load", syncSelection); map.remove(); });
    };
    setError(null);
    try {
      const corners = overlays.bounds;
      const l = createRadarMap(lRef.current, bbox, {
        url: overlays.l_png,
        corners,
        resampling: "nearest",
        outline: areas,
        selectedArea: selectedRef.current,
      }, { zoomButtons: true });
      maps.push(l);
      if (result.s1 && cRef.current) {
        const c = createRadarMap(
          cRef.current, bbox,
          { url: overlays.c_png, corners, resampling: "nearest", outline: areas, selectedArea: selectedRef.current },
          { zoomButtons: true },
        );
        maps.push(c);
        stopSync = syncMaps(l, c);
      }
      maps.forEach((map) => map.on("load", syncSelection));
      stopResize = observeMaps(wrapRef.current, maps);
    } catch {
      cleanup();
      setError("The radar comparison could not be displayed in this browser.");
    }
    return cleanup;
  }, [bbox, overlays, areas, result.s1]);

  useEffect(() => { mapsRef.current.forEach((map) => updateSelectedArea(map, selectedArea)); }, [selectedArea]);

  const example = result.fixture && <span className="rv-example">Example data</span>;
  const passLabel = (dates: string[]) =>
    `${dates.length} ${dates.length === 1 ? "pass" : "passes"} · ` +
    `${formatPass(dates[0]) ?? "Unknown date"} – ${formatPass(dates[dates.length - 1]) ?? "Unknown date"}`;
  const differentPasses = result.s1 && (result.nisar.dates.length !== result.s1.dates.length ||
    result.nisar.dates.some((date, i) => date.slice(0, 10) !== result.s1?.dates[i]?.slice(0, 10)));

  return (
    <div className="rv-lc" ref={wrapRef} role="region" aria-label="L-band vs C-band side by side">
      <div className="rv-pane">
        <div className="rv-map" ref={lRef} aria-label="NISAR relative backscatter change map" />
        <div className="rv-card" role="group" aria-label="NISAR L-band">
          <div className="rv-sensor">
            NISAR <span>L-band, 24 cm waves</span>
          </div>
          <div className="rv-period">{passLabel(result.nisar.dates)}</div>
          <div className="rv-total">{formatHa(totals.onlyNisar)} NISAR-majority area</div>
          <Breakdown both={totals.both} />
          {example}
        </div>
      </div>
      <div className="rv-pane">
        {result.s1 ? <div className="rv-map" ref={cRef} aria-label="Sentinel-1 relative backscatter change map" /> :
          <div className="rv-empty" role="status">No Sentinel-1 pair is available for this box.</div>}
        <div className="rv-card" role="group" aria-label="Sentinel-1 C-band">
          <div className="rv-sensor">
            Sentinel-1 <span>C-band, 5.6 cm waves</span>
          </div>
          {result.s1 && <div className="rv-period">{passLabel(result.s1.dates)}</div>}
          {result.s1 ? (
            <>
              <div className="rv-total">{formatHa(totals.onlyS1)} Sentinel-1-majority area</div>
              <Breakdown both={totals.both} />
            </>
          ) : (
            <div className="rv-total rv-none">Change area unavailable</div>
          )}
          {example}
        </div>
      </div>
      <div className="rv-delta-key" aria-label="Relative backscatter change colors">
        <span><i className="rv-drop" />Lower backscatter</span>
        <span><i className="rv-rise" />Higher backscatter</span>
        <span>All candidate patches are outlined on both maps. Category areas are whole patches, not exact per-sensor detected hectares.</span>
        {differentPasses && <span>Pass dates or counts differ; matched-pair metrics are in the scorecard.</span>}
      </div>
      {error && <div className="rv-note" role="alert">{error}</div>}
    </div>
  );
}

function Breakdown({ both }: { both: number }) {
  return (
    <div className="rv-split">
      <span>
        <i style={{ background: AGREEMENT_COLORS.both }} />
        {formatHa(both)} both / mixed area
      </span>
    </div>
  );
}

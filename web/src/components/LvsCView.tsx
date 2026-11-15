// L-band vs C-band: NISAR and Sentinel-1 change images side by side on synced maps, with per-sensor hectares (Task B5).
import "maplibre-gl/dist/maplibre-gl.css";
import "./ComparisonViews.css";
import { useEffect, useMemo, useRef, useState } from "react";
import { AGREEMENT_COLORS, type Result } from "../types.ts";
import { createRadarMap, formatHa, formatPass, observeMaps, sensorTotals, syncMaps } from "./comparisonmaphelpers.ts";

export interface LvsCViewProps {
  result: Result;
}

export default function LvsCView({ result }: LvsCViewProps) {
  const { bbox, overlays, areas } = result;
  const lRef = useRef<HTMLDivElement>(null);
  const cRef = useRef<HTMLDivElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const totals = useMemo(() => sensorTotals(areas), [areas]);

  useEffect(() => {
    if (!lRef.current || !wrapRef.current) return;
    const maps: ReturnType<typeof createRadarMap>[] = [];
    let stopSync = () => {};
    let stopResize = () => {};
    const cleanup = () => {
      stopResize();
      stopSync();
      maps.splice(0).forEach((map) => map.remove());
    };
    setError(null);
    try {
      const corners = overlays.bounds;
      const l = createRadarMap(lRef.current, bbox, {
        url: overlays.l_png,
        corners,
        resampling: "nearest",
        outline: areas.filter((a) => a.agreement !== "C"),
      }, { zoomButtons: true });
      maps.push(l);
      if (result.s1 && cRef.current) {
        const c = createRadarMap(
          cRef.current, bbox,
          { url: overlays.c_png, corners, resampling: "nearest", outline: areas.filter((a) => a.agreement !== "L") },
          { zoomButtons: true },
        );
        maps.push(c);
        stopSync = syncMaps(l, c);
      }
      stopResize = observeMaps(wrapRef.current, maps);
    } catch {
      cleanup();
      setError("The radar comparison could not be displayed in this browser.");
    }
    return cleanup;
  }, [bbox, overlays, areas, result.s1]);

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
          <div className="rv-total">{formatHa(totals.nisar)} changed</div>
          <Breakdown only={totals.onlyNisar} onlyLabel="only NISAR" onlyColor={AGREEMENT_COLORS.L} both={totals.both} />
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
              <div className="rv-total">{formatHa(totals.s1)} changed</div>
              <Breakdown only={totals.onlyS1} onlyLabel="only Sentinel-1" onlyColor={AGREEMENT_COLORS.C} both={totals.both} />
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
        <span>Changed-area totals include overlap.</span>
        {differentPasses && <span>Pass dates or counts differ; matched-pair metrics are in the scorecard.</span>}
      </div>
      {error && <div className="rv-note" role="alert">{error}</div>}
    </div>
  );
}

function Breakdown({ only, onlyLabel, onlyColor, both }: { only: number; onlyLabel: string; onlyColor: string; both: number }) {
  return (
    <div className="rv-split">
      <span>
        <i style={{ background: onlyColor }} />
        {Math.round(only).toLocaleString("en-US")} {onlyLabel}
      </span>
      <span>
        <i style={{ background: AGREEMENT_COLORS.both }} />
        {Math.round(both).toLocaleString("en-US")} both
      </span>
    </div>
  );
}

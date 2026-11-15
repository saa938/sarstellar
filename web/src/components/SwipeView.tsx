// Before | After: drag a divider across the radar images of the first and last NISAR passes (Task B5).
import "maplibre-gl/dist/maplibre-gl.css";
import "@maplibre/maplibre-gl-compare/dist/maplibre-gl-compare.css";
import "./ComparisonViews.css";
import { useEffect, useRef, useState } from "react";
import type { ChangeArea, Result } from "../types.ts";
import { createRadarMap, formatPass, loadCompare, observeMaps, updateSelectedArea, type CompareControl } from "./comparisonmaphelpers.ts";

export interface SwipeViewProps {
  result: Result;
  selectedArea?: ChangeArea | null;
}

export default function SwipeView({ result, selectedArea = null }: SwipeViewProps) {
  const { bbox, overlays, nisar } = result;
  const wrapRef = useRef<HTMLDivElement>(null);
  const beforeRef = useRef<HTMLDivElement>(null);
  const afterRef = useRef<HTMLDivElement>(null);
  const compareRef = useRef<CompareControl | null>(null);
  const mapsRef = useRef<ReturnType<typeof createRadarMap>[]>([]);
  const selectedRef = useRef(selectedArea);
  selectedRef.current = selectedArea;
  const percentRef = useRef(50);
  const [percent, setPercent] = useState(50);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap || !beforeRef.current || !afterRef.current) return;
    const maps: ReturnType<typeof createRadarMap>[] = [];
    mapsRef.current = maps;
    const syncSelection = () => maps.forEach((map) => updateSelectedArea(map, selectedRef.current));
    let cancelled = false;
    let stopResize = () => {};
    setError(null);
    setPercent(50);
    percentRef.current = 50;
    const cleanup = () => {
      cancelled = true;
      stopResize();
      compareRef.current?.remove(); // before the maps: Compare resets their clipping and sync
      compareRef.current = null;
      maps.splice(0).forEach((map) => { map.off("load", syncSelection); map.remove(); });
    };
    try {
      const corners = overlays.bounds;
      const before = createRadarMap(beforeRef.current, bbox, { url: overlays.before_png, corners, selectedArea: selectedRef.current });
      maps.push(before);
      const after = createRadarMap(afterRef.current, bbox, { url: overlays.after_png, corners, selectedArea: selectedRef.current }, { zoomButtons: true });
      maps.push(after);
      maps.forEach((map) => map.on("load", syncSelection));
      stopResize = observeMaps(wrap, maps, () => {
        compareRef.current?.setSlider((percentRef.current / 100) * wrap.clientWidth);
      });
      loadCompare().then(
        (Compare) => {
          if (cancelled) return;
          try {
            const compare = new Compare(before, after, wrap);
            compare.on("slideend", ({ currentPosition }) => {
              if (wrap.clientWidth > 0) {
                percentRef.current = Math.max(0, Math.min(100, Math.round((currentPosition / wrap.clientWidth) * 100)));
                setPercent(percentRef.current);
              }
            });
            compareRef.current = compare;
            wrap.querySelector(".compare-swiper-vertical")?.setAttribute("aria-hidden", "true");
          } catch {
            setError("The swipe control could not load. Reload the page to try again.");
          }
        },
        () => {
          if (!cancelled) setError("The swipe control could not load. Reload the page to try again.");
        },
      );
    } catch {
      cleanup();
      setError("Before and after imagery could not be displayed in this browser.");
    }
    return cleanup;
  }, [bbox, overlays]);

  useEffect(() => { mapsRef.current.forEach((map) => updateSelectedArea(map, selectedArea)); }, [selectedArea]);

  const moveDivider = (value: number) => {
    percentRef.current = value;
    setPercent(value);
    const width = wrapRef.current?.clientWidth ?? 0;
    compareRef.current?.setSlider((value / 100) * width);
  };

  const first = formatPass(nisar.dates[0]);
  const last = formatPass(nisar.dates[nisar.dates.length - 1]);

  return (
    <div className="rv-swipe" ref={wrapRef} role="region" aria-label="Before and after radar swipe">
      <div className="rv-map" ref={beforeRef} aria-label="Before NISAR radar image" />
      <div className="rv-map" ref={afterRef} aria-label="After NISAR radar image" />
      <span className="rv-tag rv-tag-left">{first ? `Before: NISAR ${first}` : "Before"}</span>
      <span className="rv-tag rv-tag-right">{last ? `After: NISAR ${last}` : "After"}</span>
      <input
        className="rv-range"
        type="range"
        min={0}
        max={100}
        value={percent}
        aria-label="Divider position (left shows before, right shows after)"
        aria-valuetext={`${percent}% before, ${100 - percent}% after`}
        onChange={(e) => moveDivider(Number(e.target.value))}
      />
      {error && (
        <div className="rv-note" role="alert">
          {error}
        </div>
      )}
    </div>
  );
}

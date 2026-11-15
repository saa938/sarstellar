// Default BoxDrawer: a terra-draw rectangle on the MapLibre map. Loaded lazily by DrawBox, so terra-draw
// is only fetched when someone draws a box.
import type { Map as MaplibreMap } from "maplibre-gl";
import { TerraDraw, TerraDrawRectangleMode } from "terra-draw";
import { TerraDrawMapLibreGLAdapter } from "terra-draw-maplibre-gl-adapter";
import { bboxFromRing, type BoxDrawer, type BoxListener } from "./box.ts";

type FeatureId = Parameters<TerraDraw["getSnapshotFeature"]>[0];

const MODE = "rectangle";
const BOX_COLOR = "#f59e0b";

export function createTerraDrawBoxDrawer(map: MaplibreMap): BoxDrawer {
  const draw = new TerraDraw({
    adapter: new TerraDrawMapLibreGLAdapter({ map }),
    modes: [
      new TerraDrawRectangleMode({
        // Click two corners, or press and drag.
        drawInteraction: "click-move-or-drag",
        styles: { fillColor: BOX_COLOR, fillOpacity: 0.08, outlineColor: BOX_COLOR, outlineWidth: 2 },
      }),
    ],
  });
  let listener: BoxListener | null = null;
  let started = false;
  let destroyed = false;

  const ring = (id: FeatureId) => {
    const f = draw.getSnapshotFeature(id);
    return f?.geometry.type === "Polygon" ? f.geometry.coordinates[0] : undefined;
  };

  draw.on("change", (ids, type) => {
    if (!listener) return;
    if (type === "delete") return listener(null, false);
    if (type !== "create" && type !== "update") return;
    for (const id of ids) {
      const r = ring(id);
      if (r && r.length >= 4) listener(bboxFromRing(r), false);
    }
  });

  draw.on("finish", (id, context) => {
    if (context.mode !== MODE) return;
    const r = ring(id);
    // One box at a time: stop drawing so the next click pans the map instead of starting a new box.
    draw.setMode("static");
    listener?.(r ? bboxFromRing(r) : null, true);
  });

  // terra-draw adds sources and layers, so it needs a loaded style.
  const whenReady = (fn: () => void) => {
    if (map.isStyleLoaded()) fn();
    else map.once("idle", fn);
  };

  return {
    start(l) {
      listener = l;
      whenReady(() => {
        if (destroyed || listener !== l) return;
        if (!started) {
          draw.start();
          started = true;
        }
        draw.clear();
        draw.setMode(MODE);
      });
    },
    clear() {
      listener = null;
      if (!started) return;
      draw.setMode("static");
      draw.clear();
    },
    destroy() {
      listener = null;
      destroyed = true;
      if (started) draw.stop();
      started = false;
    },
  };
}

// MapLibre 6 locates its worker at runtime with new URL("./maplibre-gl-worker.mjs", import.meta.url). Vite can't
// see that, so the worker file is never emitted (neither in dev's pre-bundled deps nor in the build) and every
// GeoJSON source fails with "Worker failed to load". Import the worker as a Vite asset and point MapLibre at it.
// Import this module for its side effect before creating a map. Any map in the app (e.g. B2's MapView) needs it too.
import { setWorkerUrl } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";

setWorkerUrl(workerUrl);

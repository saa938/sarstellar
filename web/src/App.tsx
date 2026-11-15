// App shell (Task B2): header, hash routes (Explore / Scorecard / About), and the Explore layout from
// docs/mockups/app-mockup.html with the B3 (ChangePanel, Timeline), B4 (DrawBox) and B6 (pages) pieces mounted.
import type { Map as MapLibreMap } from "maplibre-gl";
import { lazy, Suspense, useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import "./App.css";
import { loadStory, loadStoryIndex } from "./api.ts";
import { applyAppearance } from "./appearance.ts";
import { LAUNCH } from "./launch.ts";
import { formatDateRange } from "./areas.ts";
import { AreaList } from "./components/AreaList.tsx";
import CaseStudy from "./components/CaseStudy.tsx";
import { DrawBox } from "./components/DrawBox.tsx";
import MapView from "./components/MapView.tsx";
import { ExampleTag, Sidebar } from "./components/Sidebar.tsx";
import Timeline, { type DatePair } from "./components/Timeline.tsx";
import About from "./pages/About.tsx";
import ScorecardPage, { useScorecard } from "./pages/Scorecard.tsx";
import type { Agreement, Result, StoryIndexEntry } from "./types.ts";

type Route = "explore" | "scorecard" | "about";
type Mode = "change" | "swipe" | "lc";

const ChangePanel = lazy(() => import("./components/ChangePanel.tsx"));
const ResultExports = lazy(() => import("./components/ChangePanel.tsx").then((module) => ({ default: module.ResultExports })));
const SwipeView = lazy(() => import("./components/SwipeView.tsx"));
const LvsCView = lazy(() => import("./components/LvsCView.tsx"));

const ROUTE_HASH: Record<Route, string> = { explore: "#/", scorecard: "#/scorecard", about: "#/about" };

const MODES: { mode: Mode; label: string }[] = [
  { mode: "change", label: "Detected areas" },
  {
    mode: "swipe",
    label: "Before | After",
  },
  {
    mode: "lc",
    label: "L-band vs C-band",
  },
];

function routeFromHash(): Route {
  const hash = window.location.hash;
  return hash === ROUTE_HASH.scorecard ? "scorecard" : hash === ROUTE_HASH.about ? "about" : "explore";
}

function subscribeHash(onChange: () => void): () => void {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

export default function App() {
  const route = useSyncExternalStore(subscribeHash, routeFromHash);
  const scorecard = useScorecard(); // undefined while loading, null until Task C2 publishes scorecard.json
  const [stories, setStories] = useState<StoryIndexEntry[] | null>(null);
  const [storyId, setStoryId] = useState<string | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hidden, setHidden] = useState<ReadonlySet<Agreement>>(new Set());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dates, setDates] = useState<DatePair | null>(null);
  const [mode, setMode] = useState<Mode>("change");
  const [map, setMap] = useState<MapLibreMap | null>(null);
  const [layerOpacity, setLayerOpacity] = useState(0.65);
  // One dark appearance, matching the story site.
  useEffect(() => { applyAppearance("dark"); }, []);
  // Bumped by every story request and live result, so a slow story load can't replace newer content.
  const latest = useRef(0);

  const showResult = useCallback((r: Result) => {
    setResult(r);
    setSelectedId(null);
    setHidden(new Set());
    setDates(null);
  }, []);

  const openStory = useCallback(
    async (id: string) => {
      const request = ++latest.current;
      setLoading(true);
      setError(null);
      try {
        const r = await loadStory(id);
        if (request === latest.current) {
          showResult(r);
          setStoryId(id);
        }
      } catch (err) {
        if (request === latest.current) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (request === latest.current) setLoading(false);
      }
    },
    [showResult],
  );

  /** A drawn box's finished job replaces the story on the map. */
  const showLiveResult = useCallback(
    (r: Result) => {
      latest.current++;
      setStoryId(null);
      setLoading(false);
      setError(null);
      showResult(r);
    },
    [showResult],
  );

  useEffect(() => {
    let alive = true;
    void loadStoryIndex().then((list) => {
      if (!alive) return;
      setStories(list);
      const start = list.find((s) => s.id === LAUNCH.story)?.id ?? (LAUNCH.focus ? null : list[0]?.id ?? null);
      if (start) void openStory(start);
    }, () => alive && setError("The stories could not load. You can still draw a box to analyse."));
    return () => {
      alive = false;
      latest.current++;
    };
  }, [openStory]);

  const toggleAgreement = useCallback((k: Agreement) => {
    setHidden((prev) => {
      const next = new Set(prev);
      if (!next.delete(k)) next.add(k);
      return next;
    });
  }, []);

  // A ?bbox= link with no saved example frames the map there, ready to draw a box.
  useEffect(() => {
    if (!map || !LAUNCH.focus || LAUNCH.story) return;
    const [w, s, e, n] = LAUNCH.focus;
    map.fitBounds([[w, s], [e, n]], { padding: 40, duration: 0 });
  }, [map]);

  const story = stories?.find((s) => s.id === storyId) ?? null;
  const selected = result?.areas.find((a) => a.id === selectedId) ?? null;
  const visible: Record<Agreement, boolean> = { L: !hidden.has("L"), both: !hidden.has("both"), C: !hidden.has("C") };

  return (
    <div className={LAUNCH.embed ? "app app--embed" : "app"}>
      {!LAUNCH.embed && (
        <header className="top">
          <a className="logo" href="/" aria-label="SARstellar home">SAR<em>stellar</em></a>
          <span className="spacer" />
          {route === "explore" && result?.fixture && <ExampleTag />}
          <nav aria-label="Sections">
            <a href="/#/">Story</a>
            <a href="/#/places">Places</a>
            <a href="/#/method">Method</a>
            <a href="/map/" aria-current={route === "explore" ? "page" : undefined}>Analyze</a>
            {scorecard && <a href="/map/#/scorecard" aria-current={route === "scorecard" ? "page" : undefined}>Benchmark</a>}
          </nav>
        </header>
      )}

      {route === "about" && (
        <div className="pagewrap">
          <About />
        </div>
      )}
      {route === "scorecard" && (
        <div className="pagewrap">
          {scorecard ? (
            <ScorecardPage data={scorecard} />
          ) : (
            <main className="pg">
              <div className="pg-inner">
                <h1>National scorecard</h1>
                <p>{scorecard === undefined ? "Loading…" : "The national scorecard isn't published yet. Check back soon."}</p>
              </div>
            </main>
          )}
        </div>
      )}

      {/* Explore stays mounted on other pages so the map view and any running job survive. */}
      <div className="explore" hidden={route !== "explore"}>
        <Sidebar
          actions={<DrawBox map={map} dates={dates ?? undefined} onResult={showLiveResult} onStartDrawing={() => setMode("change")} />}
          stories={stories}
          activeStoryId={storyId}
          onSelectStory={(id) => void openStory(id)}
          result={result}
          hidden={hidden}
          onToggleAgreement={toggleAgreement}
          layerOpacity={layerOpacity}
          onOpacityChange={setLayerOpacity}
          layerControlsEnabled={mode === "change"}
        />

        <div className="mapwrap">
          <div className="map-pane" hidden={mode !== "change"}>
            <MapView result={result} visible={visible} selectedAreaId={selectedId} opacity={layerOpacity} onSelectArea={setSelectedId} onMapReady={setMap} />
          </div>
          <Suspense fallback={<div className="map-loading" role="status">Loading comparison…</div>}>
            {mode === "swipe" && result && <SwipeView result={result} selectedArea={selected} />}
            {mode === "lc" && result && <LvsCView result={result} selectedArea={selected} />}
          </Suspense>
          <div className="modes" role="group" aria-label="View">
            {MODES.map((m) => (
              <button key={m.mode} type="button" disabled={!result && m.mode !== "change"} aria-pressed={mode === m.mode} onClick={() => setMode(m.mode)}>
                {m.label}
              </button>
            ))}
          </div>
          {loading && <div className="map-loading" role="status">Loading saved radar analysis…</div>}
        </div>

        <aside className="side right" aria-label="Details">
          {selected && result && (
            <Suspense fallback={<p role="status">Loading change evidence…</p>}>
              <ChangePanel area={selected} result={result} scorecard={scorecard} onClose={() => setSelectedId(null)} />
            </Suspense>
          )}
            <div hidden={Boolean(selected)}>
              <Intro story={story} result={result} loading={loading} error={error} />
              <CaseStudy storyId={storyId} result={result} onSelectArea={setSelectedId} />
              {result && !loading && (
                <>
                  <Suspense fallback={null}><ResultExports files={result.exports} /></Suspense>
                  <div className="label">Detected areas</div>
                  <AreaList key={result.bbox.join(",") + result.nisar.dates.join(",")} areas={result.areas} hidden={hidden} onSelect={setSelectedId} />
                </>
              )}
            </div>
        </aside>

        <footer className="passes">{result && <Timeline dates={result.nisar.dates} value={dates} onChange={setDates} />}</footer>
      </div>
    </div>
  );
}

interface IntroProps {
  story: StoryIndexEntry | null;
  result: Result | null;
  loading: boolean;
  error: string | null;
}

function Intro({ story, result, loading, error }: IntroProps) {
  const hectares = result?.areas.reduce((sum, area) => sum + area.area_ha, 0) ?? 0;
  return (
    <>
      {story ? (
        <>
          <div className="label first">{story.place}</div>
          <h2>{story.title}</h2>
          <p className="hint">{formatDateRange(story.dates)}</p>
          {result && <p className="story-overview">
            <b>{Math.round(hectares).toLocaleString("en-US")}</b> ha detected
            <span>{result.areas.length} change areas</span>
          </p>}
          {story.summary && <details className="story-notes">
            <summary>Example notes</summary><p>{story.summary}</p>
          </details>}
          {result?.s1 && result.nisar.dates.length !== result.s1.dates.length &&
            <p className="story-caveat">{result.nisar.dates.length} NISAR observations; {result.s1.dates.length} Sentinel-1 observations. These area totals do not establish which radar performed better. See the <a href="#/scorecard">paired benchmark</a>.</p>}
        </>
      ) : (
        result && (
          <>
            <div className="label first">Live analysis</div>
            <h2>Analysis area</h2>
            <p className="hint">{formatDateRange(result.nisar.dates)}</p>
          </>
        )
      )}
      {loading && <p className="hint">Loading…</p>}
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      {result?.message && <p className="notice">{result.message}</p>}
      {result && result.areas.length > 0 && (
        <p className="hint">
          Select a polygon or a row to inspect its measurements, time series and classification.
        </p>
      )}
    </>
  );
}

// App shell (Task B2): header, hash routes (Explore / Scorecard / About), and the Explore layout from
// docs/mockups/app-mockup.html with the B3 (ChangePanel, Timeline), B4 (DrawBox) and B6 (pages) pieces mounted.
import type { Map as MapLibreMap } from "maplibre-gl";
import { lazy, Suspense, useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import "./App.css";
import { loadStory, loadStoryIndex } from "./api.ts";
import { formatDateRange } from "./areas.ts";
import { AreaList } from "./components/AreaList.tsx";
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
const SwipeView = lazy(() => import("./components/SwipeView.tsx"));
const LvsCView = lazy(() => import("./components/LvsCView.tsx"));

const ROUTE_HASH: Record<Route, string> = { explore: "#/", scorecard: "#/scorecard", about: "#/about" };

const MODES: { mode: Mode; label: string }[] = [
  { mode: "change", label: "Change map" },
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
      if (list.length > 0) void openStory(list[0].id);
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

  const story = stories?.find((s) => s.id === storyId) ?? null;
  const selected = result?.areas.find((a) => a.id === selectedId) ?? null;
  const visible: Record<Agreement, boolean> = { L: !hidden.has("L"), both: !hidden.has("both"), C: !hidden.has("C") };
  const nav: Route[] = scorecard ? ["explore", "scorecard", "about"] : ["explore", "about"];

  return (
    <div className="app">
      <header className="top">
        <a className="logo" href={ROUTE_HASH.explore}>
          SAR<span>stellar</span>
        </a>
        <span className="tagline">Two radars, one map</span>
        <span className="spacer" />
        {route === "explore" && result?.fixture && <ExampleTag />}
        <nav aria-label="Pages">
          {nav.map((r) => (
            <a key={r} href={ROUTE_HASH[r]} aria-current={route === r ? "page" : undefined}>
              {r === "explore" ? "Explore" : r === "scorecard" ? "Scorecard" : "About"}
            </a>
          ))}
        </nav>
      </header>

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
        />

        <div className="mapwrap">
          <div className="map-pane" hidden={mode !== "change"}>
            <MapView result={result} visible={visible} selectedAreaId={selectedId} onSelectArea={setSelectedId} onMapReady={setMap} />
          </div>
          <Suspense fallback={<div className="map-loading" role="status">Loading comparison…</div>}>
            {mode === "swipe" && result && <SwipeView result={result} />}
            {mode === "lc" && result && <LvsCView result={result} />}
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
          {selected && result ? (
            <Suspense fallback={<p role="status">Loading change evidence…</p>}>
              <ChangePanel area={selected} result={result} onClose={() => setSelectedId(null)} />
            </Suspense>
          ) : (
            <>
              <Intro story={story} result={result} loading={loading} error={error} />
              {result && !loading && (
                <>
                  <div className="label">Largest changes</div>
                  <AreaList areas={result.areas} hidden={hidden} onSelect={setSelectedId} />
                </>
              )}
            </>
          )}
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
            <summary>Analysis notes and limitations</summary><p>{story.summary}</p>
          </details>}
          {result?.s1 && result.nisar.dates.length !== result.s1.dates.length &&
            <p className="story-caveat">These radars use different numbers of passes. Compare accuracy in the <a href="#/scorecard">scorecard</a>.</p>}
        </>
      ) : (
        result && (
          <>
            <div className="label first">Live analysis</div>
            <h2>Your box</h2>
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
          <b>Click a colored area</b> on the map or below to see what changed, how sure we are, and the radar physics
          behind it.
        </p>
      )}
    </>
  );
}

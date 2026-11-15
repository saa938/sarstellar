import { lazy, Suspense, useEffect } from "react";
import { useRoute } from "./lib/router";
import Story from "./pages/Story"; // the default route ships in the main bundle

const Places = lazy(() => import("./pages/Places").then((m) => ({ default: m.PlacesGrid })));
const Place = lazy(() => import("./pages/Places").then((m) => ({ default: m.Place })));
const Method = lazy(() => import("./pages/Method"));
const Present = lazy(() => import("./pages/Present"));

export default function App() {
  const route = useRoute();
  useEffect(() => {
    // old links land on the new pages
    const h = window.location.hash;
    const m = h.match(/^#\/stage\/([^?]+)/);
    if (m) window.history.replaceState(null, "", `#/places/${m[1]}`);
    else if (/^#\/(explore|constellation|stages)\b/.test(h)) window.history.replaceState(null, "", "#/places");
    else if (/^#\/(proof|moves|about)\b/.test(h)) window.history.replaceState(null, "", "#/method");
    window.scrollTo(0, 0);
  }, [route.name, route.id]);
  useEffect(() => {
    const titles: Record<string, string> = {
      story: "SARstellar: reading Earth's changes in NISAR radar",
      places: "SARstellar: places",
      place: "SARstellar: a place",
      method: "SARstellar: method",
      present: "SARstellar",
    };
    document.title = titles[route.name] ?? "SARstellar";
  }, [route.name]);
  return (
    <Suspense fallback={<div className="page-fallback" />}>
      {(route.name === "story" || route.name === "notfound") && <Story />}
      {route.name === "places" && <Places />}
      {route.name === "place" && route.id && <Place id={route.id} />}
      {route.name === "method" && <Method />}
      {route.name === "present" && <Present query={route.query} />}
    </Suspense>
  );
}

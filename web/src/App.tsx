import { lazy, Suspense, useEffect } from "react";
import { useRoute } from "./lib/router";

const Landing = lazy(() => import("./pages/Landing"));
const StagePage = lazy(() => import("./pages/StagePage"));
const FieldGuide = lazy(() => import("./pages/FieldGuide"));
const Proof = lazy(() => import("./pages/Proof"));
const Explore = lazy(() => import("./pages/Explore"));
const Present = lazy(() => import("./pages/Present"));

export default function App() {
  const route = useRoute();
  useEffect(() => {
    if (route.name !== "landing") window.scrollTo(0, 0);
  }, [route.name, route.id]);
  useEffect(() => {
    const titles: Record<string, string> = {
      landing: "SARstellar: Earth is dancing",
      stage: "SARstellar: stage",
      moves: "SARstellar: field guide to the moves",
      move: "SARstellar: field guide",
      proof: "SARstellar: how we know",
      explore: "SARstellar: all stages",
    };
    document.title = titles[route.name] ?? "SARstellar";
  }, [route.name]);
  return (
    <Suspense fallback={<div className="page-fallback" />}>
      {route.name === "landing" && <Landing />}
      {route.name === "stage" && route.id && <StagePage id={route.id} query={route.query} />}
      {route.name === "moves" && <FieldGuide />}
      {route.name === "move" && route.id && <FieldGuide moveId={route.id} />}
      {route.name === "proof" && <Proof />}
      {route.name === "explore" && <Explore />}
      {route.name === "present" && <Present query={route.query} />}
      {route.name === "notfound" && <Landing />}
    </Suspense>
  );
}

import { useEffect, useState } from "react";

export interface Route {
  name: "story" | "places" | "place" | "method" | "present" | "notfound";
  id?: string;
  query: URLSearchParams;
}

export function parseHash(hash: string): Route {
  const raw = hash.replace(/^#/, "") || "/";
  const [path, qs] = raw.split("?");
  const query = new URLSearchParams(qs || "");
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  if (parts.length === 0) return { name: "story", query };
  const [a, b] = parts;
  if ((a === "places" || a === "stage") && b) return { name: "place", id: b, query };
  if (a === "places" || a === "stages" || a === "explore" || a === "constellation") return { name: "places", query };
  if (a === "method" || a === "proof" || a === "moves" || a === "about") return { name: "method", query };
  if (a === "present") return { name: "present", query };
  return { name: "notfound", query };
}

export function useRoute() {
  const [route, setRoute] = useState(() => parseHash(window.location.hash));
  useEffect(() => {
    const on = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

import { useEffect, useState } from "react";

export interface Route {
  name: "landing" | "stage" | "moves" | "move" | "proof" | "explore" | "present" | "constellation" | "notfound";
  id?: string;
  query: URLSearchParams;
}

export function parseHash(hash: string): Route {
  const raw = hash.replace(/^#/, "") || "/";
  const [path, qs] = raw.split("?");
  const query = new URLSearchParams(qs || "");
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  if (parts.length === 0) return { name: "landing", query };
  if (parts[0] === "stage" && parts[1]) return { name: "stage", id: parts[1], query };
  if (parts[0] === "moves" && parts[1]) return { name: "move", id: parts[1], query };
  if (parts[0] === "moves") return { name: "moves", query };
  if (parts[0] === "proof") return { name: "proof", query };
  if (parts[0] === "present") return { name: "present", query };
  if (parts[0] === "constellation") return { name: "constellation", query };
  if (parts[0] === "explore" || parts[0] === "stages") return { name: "explore", query };
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

export function href(path: string) {
  return `#${path}`;
}

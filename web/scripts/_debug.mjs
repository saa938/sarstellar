import { chromium } from "playwright";
const b = await chromium.launch({ args: ["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"] });
const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
p.on("console", (m) => { if (!m.text().includes("vite") && !m.text().includes("DevTools")) console.log("console", m.type(), m.text().slice(0, 300)); });
p.on("pageerror", (e) => console.log("pageerror", e.message));
p.on("response", (r) => { const u = r.url(); if (u.includes(".webp")) console.log("resp", r.status(), u.slice(-40)); });
await p.goto("http://localhost:5199/#/stage/rondonia?t=3&play=0");
await new Promise((r) => setTimeout(r, 5000));
const info = await p.evaluate(() => {
  const m = window.__map;
  if (!m) return "no map";
  const out = {};
  for (const id of ["radar0", "radar1", "radar2", "radar3", "sel"]) {
    const s = m.getSource(id);
    out[id] = { hasImage: !!s?.image, tex: !!s?.texture, loaded: s?.loaded?.(), op: m.getPaintProperty(id, "raster-opacity"), vis: m.getLayoutProperty(id, "visibility"), coords: JSON.stringify(s?.coordinates)?.slice(0, 60) };
  }
  out.zoom = m.getZoom(); out.loaded = m.loaded(); out.styleLoaded = m.isStyleLoaded(); out._loaded = m._loaded; out.fullyLoaded = m._fullyLoaded;
  out.center = m.getCenter();
  return out;
});
console.log(JSON.stringify(info, null, 1));
await b.close();

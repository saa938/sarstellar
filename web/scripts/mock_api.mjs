// A stand-in for the live API, for testing #/explore's live mode locally:
//   node scripts/mock_api.mjs            (listens on :5299)
//   VITE_API_URL=http://localhost:5299 npx vite --port 5198
// POST /dance {"bbox":[w,s,e,n]} -> {"id"}; GET /dance/{id} -> {status, progress, message};
// GET /dance/{id}/files/... serves the Village Creek fixture bundle as if it had been computed.

import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { dirname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const bundle = join(here, "..", "public", "stages-fixture", "village-creek");
const jobs = new Map();
const RUN_MS = 6000;

const cors = { "access-control-allow-origin": "*", "access-control-allow-headers": "content-type", "access-control-allow-methods": "GET,POST,OPTIONS" };

createServer(async (req, res) => {
  if (req.method === "OPTIONS") return res.writeHead(204, cors).end();
  const url = new URL(req.url, "http://x");
  const parts = url.pathname.split("/").filter(Boolean);
  if (req.method === "POST" && url.pathname === "/dance") {
    let body = "";
    for await (const c of req) body += c;
    const { bbox } = JSON.parse(body || "{}");
    const id = `job${jobs.size + 1}`;
    jobs.set(id, { start: Date.now(), bbox });
    res.writeHead(200, { ...cors, "content-type": "application/json" });
    return res.end(JSON.stringify({ id }));
  }
  if (parts[0] === "dance" && parts[1] && parts.length === 2) {
    const j = jobs.get(parts[1]);
    if (!j) return res.writeHead(404, cors).end();
    const p = Math.min(1, (Date.now() - j.start) / RUN_MS);
    const status = p >= 1 ? "done" : p < 0.1 ? "queued" : "running";
    res.writeHead(200, { ...cors, "content-type": "application/json" });
    return res.end(JSON.stringify({ status, progress: p, message: p >= 1 ? "Done" : `Reading pass ${Math.ceil(p * 28)} of 28` }));
  }
  if (parts[0] === "dance" && parts[2] === "files") {
    const rel = normalize(parts.slice(3).join("/"));
    if (rel.startsWith("..")) return res.writeHead(400, cors).end();
    try {
      const buf = await readFile(join(bundle, rel));
      const type = rel.endsWith(".json") ? "application/json" : rel.endsWith(".webp") ? "image/webp" : "application/octet-stream";
      res.writeHead(200, { ...cors, "content-type": type });
      return res.end(buf);
    } catch {
      return res.writeHead(404, cors).end();
    }
  }
  res.writeHead(404, cors).end();
}).listen(5299, () => console.log("mock live API on http://localhost:5299"));

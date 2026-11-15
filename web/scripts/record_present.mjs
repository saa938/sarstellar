// Drives #/present at 1920x1080: waits until every stage is preloaded, starts the sequence, and
// saves key frames (and, with --video, a WebM of the whole run) to web/screenshots/.
//   node scripts/record_present.mjs [--base http://localhost:5199] [--video] [--fixtures]

import { chromium } from "playwright";
import { mkdirSync, renameSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, "..", "screenshots");
mkdirSync(out, { recursive: true });
const args = process.argv.slice(2);
const base = args.includes("--base") ? args[args.indexOf("--base") + 1] : "http://localhost:5199";
const video = args.includes("--video");
const fixtures = args.includes("--fixtures");

const browser = await chromium.launch({ args: ["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"] });
const ctx = await browser.newContext({
  viewport: { width: 1920, height: 1080 },
  deviceScaleFactor: 1,
  ...(video ? { recordVideo: { dir: out, size: { width: 1920, height: 1080 } } } : {}),
});
const page = await ctx.newPage();
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(e.message));
await page.goto(`${base}/#/present?wait=1${fixtures ? "&fixtures=1" : ""}`);
await page.waitForFunction(() => window.__present?.ready === true, null, { timeout: 120000 });
const duration = await page.evaluate(() => window.__present.duration);
await page.evaluate(() => window.__present.start());
const t0 = Date.now();
const marks = [1.6, 5.2, 8.4, 11.5, 15.4, 18.9, 22.5, 26.8];
for (const m of marks) {
  const wait = m * 1000 - (Date.now() - t0);
  if (wait > 0) await new Promise((r) => setTimeout(r, wait));
  const f = join(out, `present-${String(m).replace(".", "_")}s.png`);
  await page.screenshot({ path: f });
  console.log(f);
}
const rest = (duration + 1) * 1000 - (Date.now() - t0);
if (rest > 0) await new Promise((r) => setTimeout(r, rest));
const v = page.video();
await ctx.close();
if (v) {
  const p = await v.path();
  const dest = join(out, "present.webm");
  renameSync(p, dest);
  console.log(dest);
}
await browser.close();
console.log(errors.length ? `Console errors:\n${errors.join("\n")}` : "No console errors.");

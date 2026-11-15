// Deterministic frame capture of #/present at 1920x1080 under virtual time.
// The page's clock (performance.now, requestAnimationFrame, Date.now) is frozen and advanced
// exactly 1/FPS s per frame, so the video is smooth however slowly the machine renders.
//   node scripts/record_frames.mjs --base http://localhost:4417 --out /abs/frames --fps 30

import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const args = process.argv.slice(2);
const arg = (k, d) => (args.includes(k) ? args[args.indexOf(k) + 1] : d);
const base = arg("--base", "http://localhost:4417");
const out = arg("--out", "/tmp/frames");
const fps = Number(arg("--fps", "30"));
mkdirSync(out, { recursive: true });

const virtualClock = () => {
  const realNow = performance.now.bind(performance);
  const realRaf = window.requestAnimationFrame.bind(window);
  const realCaf = window.cancelAnimationFrame.bind(window);
  const realDate = Date.now;
  let on = false;
  let vt = 0;
  let dateBase = 0;
  let next = 1;
  const cbs = new Map();
  window.__vt = {
    enable() {
      vt = realNow();
      dateBase = realDate() - vt;
      on = true;
    },
    step(ms) {
      vt += ms;
      const list = [...cbs.entries()];
      cbs.clear();
      for (const [, cb] of list) {
        try { cb(vt); } catch (e) { console.error(e); }
      }
    },
    flush() {
      const list = [...cbs.entries()];
      cbs.clear();
      for (const [, cb] of list) {
        try { cb(vt); } catch (e) { console.error(e); }
      }
    },
    pending: () => cbs.size,
  };
  performance.now = () => (on ? vt : realNow());
  Date.now = () => (on ? Math.round(dateBase + vt) : realDate());
  window.requestAnimationFrame = (cb) => {
    if (!on) return realRaf(cb);
    const k = next++;
    cbs.set(k, cb);
    return k;
  };
  window.cancelAnimationFrame = (k) => (on ? cbs.delete(k) : realCaf(k));
};

const browser = await chromium.launch({
  args: ["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"],
});
const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
await ctx.addInitScript(virtualClock);
const page = await ctx.newPage();
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(e.message));
await page.goto(`${base}/#/present?wait=1`);
await page.waitForFunction(() => window.__present?.ready === true, null, { timeout: 180000 });
await page.waitForTimeout(1500); // let tiles and images settle in real time
const duration = await page.evaluate(() => window.__present.duration);
await page.evaluate(() => { window.__vt.enable(); window.__present.start(); });
const frames = Math.ceil((duration + 0.4) * fps);
const settle = () => page.evaluate(() => new Promise((r) => setTimeout(r, 0)));
const t0 = Date.now();
for (let i = 0; i < frames; i++) {
  await page.evaluate((ms) => window.__vt.step(ms), 1000 / fps);
  await settle(); // React commits
  await page.evaluate(() => window.__vt.flush()); // draws scheduled by the commit, same time
  await settle();
  await page.screenshot({ path: join(out, `f${String(i).padStart(5, "0")}.png`) });
  if (i % 60 === 0) console.log(`frame ${i}/${frames} (${((Date.now() - t0) / 1000).toFixed(0)} s)`);
}
await browser.close();
console.log(`done: ${frames} frames at ${fps} fps -> ${out}`);
console.log(errors.length ? `console errors:\n${errors.slice(0, 10).join("\n")}` : "no console errors");

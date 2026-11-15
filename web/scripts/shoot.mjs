// Screenshots of every screen at desktop and phone sizes. With the dev or preview server running:
//   node scripts/shoot.mjs [--base http://localhost:5199] [only-these-shot-ids...]
// Writes PNGs to web/screenshots/ and prints any console errors.

import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, "..", "screenshots");
mkdirSync(out, { recursive: true });

const args = process.argv.slice(2);
let base = "http://localhost:5199";
const only = [];
for (let i = 0; i < args.length; i++) {
  if (args[i] === "--base") base = args[++i];
  else only.push(args[i]);
}

const VIEWPORTS = {
  desktop: { width: 1440, height: 900, deviceScaleFactor: 1 },
  phone: { width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function scrollTo(page, sel) {
  await page.evaluate((s) => {
    const el = document.querySelector(s);
    if (el) window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY, behavior: "instant" });
  }, sel);
}

const SHOTS = [
  { id: "story-hero", path: "#/", wait: 3500 },
  { id: "story-channels", path: "#/", wait: 2000, scrollTo: "#channels", extra: 3200 },
  { id: "story-ex-wheat", path: "#/", wait: 2000, scrollTo: "#ex-wheat", extra: 5200 },
  { id: "story-ex-rice", path: "#/", wait: 2000, scrollTo: "#ex-rice", extra: 5200 },
  { id: "story-ex-flood-trees", path: "#/", wait: 2000, scrollTo: "#ex-flood-trees", extra: 5200 },
  { id: "story-ex-forest-loss", path: "#/", wait: 2000, scrollTo: "#ex-forest-loss", extra: 5200 },
  { id: "story-ex-ice", path: "#/", wait: 2000, scrollTo: "#ex-ice", extra: 2500 },
  { id: "story-proof", path: "#/", wait: 2000, scrollTo: "#does-it-work", extra: 1800 },
  { id: "story-apps", path: "#/", wait: 2000, scrollTo: ".apps", extra: 1500 },
  { id: "places", path: "#/places", wait: 2500 },
  {
    id: "place-punjab",
    path: "#/places/punjab",
    wait: 6500,
    async act(page, vp) {
      const b = await page.evaluate(() => {
        const r = document.querySelector(".dchart--place")?.getBoundingClientRect();
        return r ? { x: r.left, y: r.top, w: r.width, h: r.height } : null;
      });
      if (!b) return;
      if (vp === "phone") await page.evaluate(() => window.scrollTo(0, document.querySelector(".dchart--place").getBoundingClientRect().top + window.scrollY - 80));
      const c = await page.evaluate(() => {
        const r = document.querySelector(".dchart--place").getBoundingClientRect();
        return { x: r.left, y: r.top, w: r.width, h: r.height };
      });
      await page.mouse.click(c.x + c.w * 0.62, c.y + c.h * 0.42);
      await sleep(900);
    },
  },
  { id: "place-greenland", path: "#/places/greenland", wait: 6000 },
  { id: "place-edouard", path: "#/places/edouard", wait: 6000 },
  { id: "method", path: "#/method", wait: 1500 },
];

const browser = await chromium.launch({ args: ["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"] });
const errors = [];
for (const [vpName, vp] of Object.entries(VIEWPORTS)) {
  const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: vp.deviceScaleFactor, isMobile: !!vp.isMobile, hasTouch: !!vp.hasTouch });
  for (const shot of SHOTS) {
    if (only.length && !only.some((o) => shot.id.startsWith(o))) continue;
    const page = await ctx.newPage();
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(`[${vpName} ${shot.id}] ${m.text()}`);
    });
    page.on("pageerror", (e) => errors.push(`[${vpName} ${shot.id}] pageerror ${e.message}`));
    await page.goto(`${base}/${shot.path}`, { waitUntil: "domcontentloaded" });
    await sleep(shot.wait);
    if (shot.scrollTo) {
      await scrollTo(page, shot.scrollTo);
      await sleep(shot.extra ?? 1000);
    }
    if (shot.act) await shot.act(page, vpName);
    const file = join(out, `${shot.id}-${vpName}.png`);
    await page.screenshot({ path: file, fullPage: false });
    console.log(file);
    await page.close();
  }
  await ctx.close();
}
await browser.close();
console.log(errors.length ? `\nConsole errors:\n${errors.join("\n")}` : "\nNo console errors.");

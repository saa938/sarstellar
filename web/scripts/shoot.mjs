// Screenshots of every screen at desktop and phone sizes, plus the stage view mid-playback with a
// brush selection and a solo card open. Usage (with the dev or preview server running):
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

async function floorBox(page) {
  return page.evaluate(() => {
    const c = document.querySelector(".stage .floor__gl");
    if (!c) return null;
    const r = c.getBoundingClientRect();
    return { x: r.left, y: r.top, w: r.width, h: r.height };
  });
}

const SHOTS = [
  { id: "landing-hero", path: "#/", wait: 3500 },
  { id: "landing-partners", path: "#/", wait: 2500, scrollTo: ".act--partners", extra: 1200 },
  { id: "landing-floor", path: "#/", wait: 2500, scrollTo: ".act--floor", extra: 2500 },
  { id: "landing-finding", path: "#/?fx=1", wait: 2500, scrollTo: ".act--finding", extra: 2500 },
  { id: "landing-moves", path: "#/", wait: 2500, scrollTo: ".act--moves", extra: 1500 },
  { id: "landing-tour", path: "#/", wait: 2500, scrollTo: ".act--tour", extra: 1500 },
  { id: "landing-proof", path: "#/", wait: 2500, scrollTo: ".act--proof", extra: 1200 },
  { id: "landing-future", path: "#/", wait: 2500, scrollTo: ".act--future", extra: 1200 },
  { id: "stage-rondonia", path: "#/stage/rondonia?t=5&play=0", wait: 4500 },
  {
    id: "stage-rondonia-brush",
    path: "#/stage/rondonia?t=3&play=0",
    wait: 4500,
    async act(page, vp) {
      const b = await floorBox(page);
      if (!b) return;
      if (vp === "desktop") {
        // brush the forest corner of the floor, then click a dot, then play
        await page.mouse.move(b.x + b.w * 0.62, b.y + b.h * 0.1);
        await page.mouse.down();
        await page.mouse.move(b.x + b.w * 0.76, b.y + b.h * 0.24, { steps: 8 });
        await page.mouse.up();
        await sleep(400);
        await page.mouse.click(b.x + b.w * 0.69, b.y + b.h * 0.17);
        await sleep(300);
        await page.keyboard.press("Space");
        await sleep(2300);
      } else {
        await page.touchscreen.tap(b.x + b.w * 0.69, b.y + b.h * 0.17);
        await sleep(600);
      }
    },
  },
  { id: "stage-greenland", path: "#/stage/greenland?t=4&play=0", wait: 4500 },
  { id: "stage-indiana", path: "#/stage/indiana?t=5&play=0", wait: 4500 },
  { id: "stage-sylhet", path: "#/stage/sylhet?t=5&play=0", wait: 4500 },
  { id: "stage-punjab-fixture", path: "#/stage/punjab?t=15&play=0", wait: 4000 },
  { id: "moves", path: "#/moves", wait: 2200 },
  { id: "move-bounce", path: "#/moves/bounce", wait: 2200 },
  { id: "proof", path: "#/proof", wait: 1500 },
  { id: "explore", path: "#/explore", wait: 4000 },
  { id: "constellation", path: "#/constellation", wait: 3000 },
];

const browser = await chromium.launch({
  args: ["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"],
});
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
      await page.evaluate((sel) => {
        const el = document.querySelector(sel);
        if (el) window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY, behavior: "instant" });
      }, shot.scrollTo);
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
if (errors.length) {
  console.log("\nConsole errors:");
  for (const e of errors) console.log(e);
} else console.log("\nNo console errors.");

// Visual QA: capture screenshots of key screens at desktop and mobile widths.
// Usage: node scripts/shots.mjs [baseUrl] [outDir]   (server must be running)
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const base = process.argv[2] ?? "http://127.0.0.1:8000";
const out = process.argv[3] ?? "../docs/screenshots";
mkdirSync(out, { recursive: true });

const pages = (process.env.SHOTS ?? "home,library,explorer,clauses,requirements,compare,about,ask").split(",");
const routes = {
  home: "/",
  library: "/standards",
  explorer: "/standards/demo-101-2026",
  clauses: "/standards/demo-101-2026?tab=clauses&clause=4.3.1",
  requirements: "/standards/demo-101-2026?tab=requirements",
  compare: "/compare?a=demo-101-2026&b=demo-102-2026",
  about: "/about",
  ask: "/ask?q=" + encodeURIComponent("What are the microbiological requirements for packaged drinking water?") + "&lang=en",
  catalogue: "/standards/is-4151-2015",
  guidance: "/standards/bis-hallmarking-faq",
};
const sizes = (process.env.SIZES ?? "desktop,mobile").split(",").map((s) => ({ name: s, ...(s === "mobile" ? { width: 390, height: 844 } : { width: 1280, height: 800 }) }));

const browser = await chromium.launch();
for (const size of sizes) {
  const ctx = await browser.newContext({ viewport: { width: size.width, height: size.height }, deviceScaleFactor: 1, locale: process.env.LOCALE ?? "en-IN" });
  if (process.env.LANG_UI) await ctx.addInitScript((l) => localStorage.setItem("bisense.lang", l), process.env.LANG_UI);
  const page = await ctx.newPage();
  page.on("console", (m) => m.type() === "error" && console.log(`[console:${size.name}]`, m.text()));
  for (const p of pages) {
    const url = base + routes[p];
    await page.goto(url, { waitUntil: "networkidle" });
    if (p === "ask") await page.waitForSelector("text=/From the sources|Most relevant clauses|isn't stated/", { timeout: Number(process.env.ASK_TIMEOUT ?? 120000) }).catch(() => {});
    if (p === "compare") await page.waitForSelector("table", { timeout: 120000 }).catch(() => {});
    await page.waitForTimeout(400);
    const file = `${out}/${p}-${size.name}${process.env.LANG_UI ? "-" + process.env.LANG_UI : ""}.png`;
    await page.screenshot({ path: file, fullPage: process.env.FULL === "1" });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    console.log(`${file}${overflow ? "  !! horizontal overflow" : ""}`);
  }
  await ctx.close();
}
await browser.close();

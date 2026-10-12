// Answer-page screenshots + layout checks at 1366 px and 390 px (usability pass, 2026-10-12).
// Usage: node scripts/answer-shots.mjs [baseUrl] [outDir]   (server must be running on the official index)
// Checks, printed as PASS/FAIL and reflected in the exit code:
//   - helmet answer: verdict, IS 4151 and the steps are visible on the first screen without scrolling
//   - every answer on a phone is at most 2 screens tall before "Show proof and details" is opened
//   - no horizontal overflow; the follow-up box does not overlap the verdict card
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const base = process.argv[2] ?? "http://127.0.0.1:8000";
const out = process.argv[3] ?? "../docs/screenshots";
mkdirSync(out, { recursive: true });

const ask = (q) => `/ask?q=${encodeURIComponent(q)}&lang=en`;
const screens = [
  { name: "home", url: "/" },
  { name: "answer-helmet", url: ask("Do I need BIS certification for two-wheeler helmets?"), answer: true, firstScreen: true },
  { name: "answer-tmt", url: ask("What standard for steel TMT bars?"), answer: true },
  { name: "answer-not-found", url: ask("standard for cotton t-shirts"), answer: true },
  { name: "standard-is-4151", url: "/standards/is-4151-2015" },
];
const sizes = [
  { name: "1366", width: 1366, height: 768 },
  { name: "390", width: 390, height: 844 },
];

let failed = 0;
const check = (ok, msg) => {
  console.log(`${ok ? "PASS" : "FAIL"}  ${msg}`);
  if (!ok) failed++;
};

const browser = await chromium.launch({ executablePath: process.env.PW_CHROMIUM_PATH || undefined });
for (const size of sizes) {
  const ctx = await browser.newContext({ viewport: { width: size.width, height: size.height }, deviceScaleFactor: 1 });
  await ctx.addInitScript(() => localStorage.setItem("bisense.lang", "en"));
  const page = await ctx.newPage();
  page.on("console", (m) => m.type() === "error" && console.log(`[console:${size.name}]`, m.text()));
  for (const s of screens) {
    await page.goto(base + s.url, { waitUntil: "networkidle" });
    if (s.answer) await page.waitForSelector("[data-testid=verdict-card], [data-testid=not-found]", { timeout: 120000 });
    await page.waitForTimeout(400);
    const file = `${out}/${s.name}-${size.name}.png`;
    await page.screenshot({ path: file });
    const m = await page.evaluate(() => {
      const box = (sel) => document.querySelector(sel)?.getBoundingClientRect();
      const card = box("[data-testid=verdict-card]") ?? box("[data-testid=not-found]");
      const follow = document.querySelector("main form[role=search]")?.getBoundingClientRect();
      return {
        overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
        docH: document.documentElement.scrollHeight,
        vh: window.innerHeight,
        cardBottom: card ? card.bottom + window.scrollY : null,
        followTop: follow ? follow.top + window.scrollY : null,
        chip: box("[data-testid=standard-chip]")?.bottom ?? null,
        steps: [...document.querySelectorAll("[data-testid=verdict-card] ol li")].map((li) => li.getBoundingClientRect().bottom),
        chipText: document.querySelector("[data-testid=standard-chip]")?.textContent ?? "",
      };
    });
    console.log(`${file}  height ${m.docH}px (${(m.docH / m.vh).toFixed(2)} screens)`);
    check(!m.overflow, `${s.name} @${size.name}: no horizontal overflow`);
    if (s.answer) {
      check(m.docH <= 2 * m.vh || size.name !== "390", `${s.name} @${size.name}: at most 2 screens tall before the proof is opened`);
      if (m.followTop !== null && m.cardBottom !== null) check(m.followTop >= m.cardBottom, `${s.name} @${size.name}: follow-up box does not overlap the answer`);
    }
    if (s.firstScreen) {
      check(/IS 4151/.test(m.chipText), `${s.name} @${size.name}: standard chip shows IS 4151`);
      check(m.chip !== null && m.chip <= m.vh && m.steps.length === 3 && Math.max(...m.steps) <= m.vh, `${s.name} @${size.name}: verdict, IS 4151 and the 3 steps visible without scrolling`);
    }
  }
  await ctx.close();
}
await browser.close();
console.log(failed ? `${failed} check(s) failed` : "all checks passed");
process.exit(failed ? 1 : 0);

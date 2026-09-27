// Debug helper: list elements wider than the viewport at mobile width.
// Usage: node scripts/overflow.mjs [url]
import { chromium } from "@playwright/test";

const url = process.argv[2] ?? "http://127.0.0.1:8000/";
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 390, height: 844 } });
await p.goto(url, { waitUntil: "networkidle" });
const res = await p.evaluate(() => {
  const w = window.innerWidth;
  return [...document.querySelectorAll("body *")]
    .filter((e) => e.getBoundingClientRect().right > w + 1)
    .slice(0, 12)
    .map((e) => `${e.tagName}.${(e.className || "").toString().slice(0, 80)} right=${Math.round(e.getBoundingClientRect().right)}`);
});
console.log(res.join("\n") || "no overflow");
await b.close();

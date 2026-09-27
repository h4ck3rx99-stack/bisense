// Simulates the demo script (docs/DEMO_SCRIPT.md) in a real browser and saves a screenshot per step.
// Usage: node scripts/demo-walkthrough.mjs [baseUrl]   (server must be running)
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const base = process.argv[2] ?? "http://127.0.0.1:8000";
const out = "../docs/screenshots";
mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
const answered = () => page.getByText(/From the sources|Most relevant clauses|isn't stated|Which product do you make|स्रोतों से|सबसे प्रासंगिक खंड/).first().waitFor({ timeout: 120000 });
const t0 = Date.now();
const step = async (name) => {
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${out}/demo-${name}.png` });
  console.log(`${((Date.now() - t0) / 1000).toFixed(1)}s  ${name}`);
};

await page.goto(base + "/");
await page.getByText("What BIS standards apply to packaged drinking water?").click();
await answered();
await step("1-discover");
const follow = page.getByRole("textbox", { name: "Ask a follow-up question" });
await follow.fill("What are the testing requirements?");
await follow.press("Enter");
await page.getByText("Continuing with").waitFor({ timeout: 60000 });
await page.waitForFunction(() => document.querySelectorAll("article[aria-labelledby^=q-]").length >= 2 && !document.querySelector("[aria-busy=true]"), null, { timeout: 120000 }).catch(() => {});
await page.waitForTimeout(8000);
await step("2-followup");
await page.goto(base + "/ask?q=" + encodeURIComponent("What requirements apply to my product?") + "&lang=en");
await answered();
await step("3-clarify");
await page.getByRole("button", { name: "two-wheeler helmet" }).click();
await page.getByText(/From the sources|Most relevant clauses/).nth(0).waitFor({ timeout: 120000 });
await page.waitForTimeout(3000);
await step("4-helmet");
await page.goto(base + "/");
await page.getByRole("button", { name: "हिन्दी" }).click();
await page.getByText("पैकेज्ड पेयजल के लिए कौन-से BIS मानक लागू होते हैं?").click();
await answered();
await step("5-hindi");
await page.getByRole("button", { name: "English" }).click();
await page.goto(base + "/ask?q=" + encodeURIComponent("What is the fine for selling uncertified helmets in Karnataka?") + "&lang=en");
await answered();
await step("6-refusal");
console.log("console errors:", errors.length ? errors : "none");
await browser.close();

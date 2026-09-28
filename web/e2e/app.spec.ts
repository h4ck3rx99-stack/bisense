import { expect, expectNoSeriousA11yIssues, test, waitForAnswer } from "./fixtures";

test("home loads with real library counts and is accessible", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Find the BIS standards for what you make");
  await expect(page.getByRole("link", { name: "Find standards for my product" })).toBeVisible();
  await expect(page.getByText(/BISense currently covers/)).toBeVisible();
  // sample mode (the e2e index) is announced, never passed off as official
  await expect(page.getByText("Sample, not official").first()).toBeVisible();
  await expectNoSeriousA11yIssues(page);
});

test("search from home: evidence renders, then a cited answer", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("textbox", { name: /Ask about Indian Standards/ }).fill("What are the microbiological requirements for packaged drinking water?");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/ask\?q=/);
  const firstCard = page.locator("article[id^=evidence-]").first();
  await expect(firstCard).toBeVisible();
  await waitForAnswer(page);
  await expect(page.getByRole("heading", { name: "Key points, from the source" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Next step" })).toBeVisible();
  await expect(page.locator("button[aria-label^='Source 1']").first()).toBeVisible();
  await expectNoSeriousA11yIssues(page);
});

test("citation chip -> evidence card -> exact clause opens highlighted", async ({ page }) => {
  await page.goto("/ask?q=" + encodeURIComponent("What is the maximum mass of a two-wheeler helmet?") + "&lang=en");
  await waitForAnswer(page);
  const chip = page.locator("button[aria-label^='Source ']").first();
  await chip.focus();
  await expect(page.getByRole("dialog").or(page.locator("[data-radix-popper-content-wrapper]")).first()).toBeVisible();
  await chip.click();
  const card = page.locator("article[id^=evidence-]").first();
  await card.getByRole("link", { name: "Open clause" }).click();
  await expect(page).toHaveURL(/\/standards\/demo-201-2026\?tab=clauses&clause=/);
  const clause = new URL(page.url()).searchParams.get("clause")!;
  const anchor = "clause-" + clause.replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "");
  await expect(page.locator(`#${anchor}`)).toBeVisible();
  await expect(page.locator(`#${anchor}`)).toHaveClass(/ring-1/);
});

test("follow-up question carries the standard in scope", async ({ page }) => {
  await page.goto("/ask?q=" + encodeURIComponent("What is the maximum mass of a two-wheeler helmet?") + "&lang=en");
  await waitForAnswer(page);
  const follow = page.getByRole("textbox", { name: "Ask a follow-up question" });
  await follow.fill("What must be marked on it?");
  await follow.press("Enter");
  await expect(page.getByText("Continuing with")).toBeVisible();
  await expect(page.getByText("DEMO-201:2026").first()).toBeVisible();
});

test("honest refusal for an unanswerable question", async ({ page }) => {
  await page.goto("/ask?q=" + encodeURIComponent("What is the boiling point of mercury on Mars in kelvin?") + "&lang=en");
  await expect(page.getByText("This isn't stated in the indexed sources.")).toBeVisible({ timeout: 60_000 });
});

test("language switch changes the interface language", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "हिन्दी" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "hi");
  await expect(page.getByRole("link", { name: "मानक" }).first()).toBeVisible();
  await page.getByRole("button", { name: "ಕನ್ನಡ" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "kn");
  await page.getByRole("button", { name: "English" }).click();
});

test("explorer tabs, requirements CSV and checklist", async ({ page }) => {
  await page.goto("/standards/demo-101-2026");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Illustrative Packaged Drinking Water Specification");
  await expect(page.getByText("At a glance")).toBeVisible();
  await expect(page.getByText("DEMO-101:2026").first()).toBeVisible();
  await expectNoSeriousA11yIssues(page);
  await page.getByRole("tab", { name: /Full text & clauses/ }).click();
  await expect(page.getByText("Coliform bacteria shall be absent in any 250 ml sample of the water.")).toBeVisible();
  await page.getByRole("tab", { name: /Important requirements/ }).click();
  await expect(page.getByText(/study aid, not a certification/)).toBeVisible();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: "Export CSV" }).click()]);
  expect(download.suggestedFilename()).toBe("demo-101-2026-requirements.csv");
  await page.getByRole("tab", { name: "Related & compare" }).click();
  await expect(page.getByText("Similar scope (computed)")).toBeVisible();
  await page.goto("/standards/demo-101-2026/checklist");
  await expect(page.getByRole("heading", { name: /Requirements checklist/ })).toBeVisible();
});

test("catalogue-only entry shows official compulsory-certification evidence", async ({ page, request }) => {
  test.skip((await request.get("/api/standards/is-4151-2015")).status() === 404, "official data not loaded (npm run fetch-public && npm run ingest)");
  await page.goto("/standards/is-4151-2015");
  await expect(page.getByText("Metadata only. Full text not indexed.").first()).toBeVisible();
  await expect(page.getByText(/Listed as under compulsory BIS certification/)).toBeVisible();
});

test("library filters and compare with numeric alignment", async ({ page }) => {
  await page.goto("/standards?kind=standard");
  await expect(page.getByText("4 results")).toBeVisible();
  await expectNoSeriousA11yIssues(page);
  await page.goto("/compare?a=demo-101-2026&b=demo-102-2026");
  await expect(page.getByRole("heading", { name: "Numeric limits (verbatim)" })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("rowheader", { name: /Total dissolved solids/ })).toBeVisible();
  await expect(page.getByText("150 to 700")).toBeVisible();
  await expectNoSeriousA11yIssues(page);
});

test("about page shows provenance and disclaimer; 404 page", async ({ page }) => {
  await page.goto("/about");
  await expect(page.getByText(/not an official BIS service/).first()).toBeVisible();
  await expectNoSeriousA11yIssues(page);
  await page.goto("/no/such/page");
  await expect(page.getByText("Page not found")).toBeVisible();
});

test("guided path: goal -> category from the data -> real standards -> open one", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Find standards for my product" }).click();
  await expect(page.getByRole("heading", { name: "Which product?" })).toBeVisible();
  await page.getByRole("button", { name: /Automotive and road safety/ }).click();
  await expect(page.getByText(/Automotive and road safety: 1 in the library/)).toBeVisible();
  await page.getByRole("link", { name: "Open" }).first().click();
  await expect(page).toHaveURL(/\/standards\/demo-201-2026/);
  await expectNoSeriousA11yIssues(page);
});

test("guided path: describing a product asks through the normal pipeline", async ({ page }) => {
  await page.goto("/guide");
  await page.getByRole("button", { name: "Safety requirements" }).click();
  await page.getByLabel("Describe the product in a few words").fill("two-wheeler helmet");
  await page.getByRole("button", { name: /Find/ }).click();
  await expect(page).toHaveURL(/\/ask\?q=What\+are\+the\+safety|\/ask\?q=What%20are%20the%20safety/);
  await waitForAnswer(page);
});

test("next-step chip 'Ask in हिंदी' switches the whole interface and re-asks", async ({ page }) => {
  await page.goto("/ask?q=" + encodeURIComponent("What is the maximum mass of a two-wheeler helmet?") + "&lang=en");
  await waitForAnswer(page);
  await page.getByRole("button", { name: "Ask in हिंदी" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "hi");
  await expect(page).toHaveURL(/lang=hi/);
  await expect(page.getByRole("heading", { name: "मुख्य बातें, स्रोत से" }).or(page.getByText("सबसे प्रासंगिक खंड")).first()).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "English", exact: true }).click();
});

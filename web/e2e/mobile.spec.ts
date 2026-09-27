import { expect, expectNoSeriousA11yIssues, test, waitForAnswer } from "./fixtures";

test.describe("mobile 390x844", () => {
  test("J1 discover: answer and evidence tabs, no horizontal scroll", async ({ page }) => {
    await page.goto("/ask?q=" + encodeURIComponent("What BIS standards apply to packaged drinking water?") + "&lang=en");
    await waitForAnswer(page);
    const evidenceTab = page.getByRole("tab", { name: /Evidence \(\d+\)/ });
    await expect(evidenceTab).toBeVisible();
    await evidenceTab.click();
    await expect(page.locator("article[id^=evidence-]").first()).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    expect(overflow).toBe(false);
    await expectNoSeriousA11yIssues(page);
  });

  test("J2 follow-up keeps context", async ({ page }) => {
    await page.goto("/ask?q=" + encodeURIComponent("What is the minimum elongation for DFe 500 TMT bars?") + "&lang=en");
    await waitForAnswer(page);
    const follow = page.getByRole("textbox", { name: "Ask a follow-up question" });
    await follow.fill("How are samples selected?");
    await follow.press("Enter");
    await expect(page.getByText("Continuing with")).toBeVisible();
  });

  test("J7 Kannada interface and query", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "ಕನ್ನಡ" }).click();
    await expect(page.locator("html")).toHaveAttribute("lang", "kn");
    await page.getByRole("textbox").first().fill("ಚಿನ್ನದ ಆಭರಣಕ್ಕೆ ಹಾಲ್‌ಮಾರ್ಕ್ ಹೇಗೆ ಪರಿಶೀಲಿಸುವುದು?");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("tab", { name: /ಸಾಕ್ಷ್ಯ/ })).toBeVisible({ timeout: 60_000 });
    await page.getByRole("button", { name: "English" }).click();
  });
});

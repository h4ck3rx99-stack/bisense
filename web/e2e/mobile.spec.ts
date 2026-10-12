import { expect, expectNoSeriousA11yIssues, openProof, test, waitForAnswer } from "./fixtures";

test.describe("mobile 390x844", () => {
  test("J1 discover: verdict first, at most 2 screens, evidence inside the details, no horizontal scroll", async ({ page }) => {
    await page.goto("/ask?q=" + encodeURIComponent("What BIS standards apply to packaged drinking water?") + "&lang=en");
    await waitForAnswer(page);
    await expect(page.getByTestId("verdict-card")).toBeVisible();
    const tall = await page.evaluate(() => document.documentElement.scrollHeight / window.innerHeight);
    expect(tall).toBeLessThanOrEqual(2);
    // the follow-up box sits after the answer, not over it
    const [cardBottom, followTop] = await page.evaluate(() => [
      document.querySelector("[data-testid=verdict-card]")!.getBoundingClientRect().bottom,
      document.querySelector("main form[role=search]")!.getBoundingClientRect().top,
    ]);
    expect(followTop).toBeGreaterThanOrEqual(cardBottom);
    await openProof(page);
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
    await waitForAnswer(page);
    await expect(page.getByRole("button", { name: "ಪುರಾವೆ ಮತ್ತು ವಿವರ ತೋರಿಸಿ" }).or(page.getByTestId("not-found")).first()).toBeVisible();
    await page.getByRole("button", { name: "English" }).click();
  });
});

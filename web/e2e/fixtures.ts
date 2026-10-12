import { test as base, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// Every test fails if the page logs a console error. Tests that deliberately provoke an HTTP error
// response (e.g. a failing speech service) list the expected messages in `allowedConsoleErrors`.
export const test = base.extend<{ consoleErrors: string[]; allowedConsoleErrors: RegExp[] }>({
  allowedConsoleErrors: [[], { option: true }],
  consoleErrors: [
    async ({ page, allowedConsoleErrors }, use) => {
      const errors: string[] = [];
      page.on("console", (m) => {
        if (m.type() === "error" && !allowedConsoleErrors.some((r) => r.test(m.text()))) errors.push(m.text());
      });
      page.on("pageerror", (e) => errors.push(String(e)));
      await use(errors);
      expect(errors, `console errors:\n${errors.join("\n")}`).toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };

export async function expectNoSeriousA11yIssues(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious.map((v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(", ")})`)).toEqual([]);
}

/** An answer has arrived: the verdict card, the "not found" card, the details (answers without a verdict) or
 *  the product clarification. */
export async function waitForAnswer(page: Page) {
  await expect(page.locator("[data-testid=verdict-card], [data-testid=not-found], [data-testid=proof]").or(page.getByText(/Which product do you make/)).first()).toBeVisible({ timeout: 60_000 });
}

/** Open "Show proof and details" on the latest answer (evidence, key points, next steps live behind it). */
export async function openProof(page: Page) {
  const toggle = page.getByTestId("toggle-proof").last();
  if ((await toggle.count()) && (await toggle.getAttribute("aria-expanded")) !== "true") await toggle.click();
  await expect(page.getByTestId("proof").last()).toBeVisible();
}

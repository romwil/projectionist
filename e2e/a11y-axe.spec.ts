import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { mockCuratorApis, mockFeatures, resetMockCertifications } from "./fixtures/api-mocks";

// A11Y-012: axe on ten routes in Lights Up and Lights Down. Fails on serious or
// critical WCAG 2 A/AA violations. Automated checks find roughly a third of real
// barriers; keyboard and screen-reader passes still happen in Interactive UI QA.

const ROUTES = [
  "/chat",
  "/explore",
  "/library",
  "/search",
  "/inbox",
  "/live",
  "/settings/profile",
  "/settings/privacy",
  "/admin",
  "/privacy",
] as const;

const THEMES = [
  { stored: "lights_up", attr: "lights-up" },
  { stored: "lights_down", attr: "lights-down" },
] as const;

async function useTheme(page: Page, stored: string) {
  await page.addInitScript((value) => {
    localStorage.setItem("projectionist.ui_theme", value);
  }, stored);
  await page.route("**/api/auth/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        authenticated: true,
        user: {
          id: "bootstrap-owner",
          display_name: "Owner",
          role: "owner",
          ui_theme: stored,
          ui_font_size: "medium",
        },
      }),
    });
  });
}

for (const theme of THEMES) {
  test.describe(`axe (${theme.attr})`, () => {
    test.beforeEach(async ({ page }) => {
      resetMockCertifications();
      await mockCuratorApis(page);
      await mockFeatures(page);
      await useTheme(page, theme.stored);
    });

    for (const route of ROUTES) {
      test(`${route} has no serious or critical violations`, async ({ page }) => {
        await page.goto(route);
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme.attr);
        await page.locator("#root *").first().waitFor();
        await page.waitForLoadState("load");
        await page.waitForTimeout(400);
        const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
        const blocking = results.violations
          .filter((v) => v.impact === "serious" || v.impact === "critical")
          .map((v) => ({
            id: v.id,
            impact: v.impact,
            help: v.help,
            targets: v.nodes.slice(0, 5).map((n) => n.target.join(" ")),
            summary: v.nodes[0]?.failureSummary,
          }));
        expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([]);
      });
    }
  });
}

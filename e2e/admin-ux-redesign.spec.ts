import { expect, test } from "@playwright/test";
import { mockCuratorApis, resetMockCertifications } from "./fixtures/api-mocks";
import { completeOnboardingViaApi } from "./fixtures/helpers";

test.describe("Admin UX redesign Phase 1", () => {
  test.beforeEach(async ({ page, request }) => {
    resetMockCertifications();
    await completeOnboardingViaApi(request);
    await mockCuratorApis(page);
  });

  test("overview keeps Needs attention first under compact Admin shell", async ({ page }) => {
    await page.goto("/admin/overview");
    await page.getByTestId("admin-overview-page").waitFor();
    await expect(page.getByTestId("admin-layout")).toHaveAttribute("data-density", "compact");
    await expect(page.getByTestId("owner-needs-attention")).toBeVisible();
    await expect(page.getByTestId("admin-nav-group-heading-setup")).toBeVisible();
    await expect(page.getByTestId("admin-nav-group-heading-members")).toBeVisible();
    await expect(page.getByTestId("admin-nav-live-channels")).toHaveText(/Live/);
    await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();

    const attentionBox = await page.getByTestId("owner-needs-attention").boundingBox();
    const healthBox = await page.getByTestId("household-health-hero").boundingBox();
    expect(attentionBox && healthBox && attentionBox.y <= healthBox.y).toBeTruthy();
  });

  test("libraries hub shows sticky subnav and Sync panel", async ({ page }) => {
    await page.goto("/admin/libraries");
    await expect(page.getByRole("heading", { name: "Libraries", level: 1 })).toBeVisible();
    await expect(page.getByTestId("libraries-hub")).toBeVisible();
    await expect(page.getByTestId("libraries-hub-subnav")).toBeVisible();
    await expect(page.getByTestId("libraries-hub-tab-sync")).toBeVisible();
    await expect(page.getByTestId("libraries-hub-tab-repair")).toBeVisible();
    await expect(page.getByTestId("library-sync-card")).toBeVisible();
    await expect(page.getByTestId("library-sync-button")).toBeVisible();

    await page.getByTestId("libraries-hub-tab-plex").click();
    await expect(page.getByTestId("plex-library-mapping")).toBeVisible();
  });

  test("members and live aliases redirect", async ({ page }) => {
    await page.goto("/admin/members");
    await expect(page).toHaveURL(/\/admin\/household/);
    await page.goto("/admin/live");
    await expect(page).toHaveURL(/\/admin\/live-channels/);
  });
});

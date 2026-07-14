import { expect, test } from "@playwright/test";
import {
  mockCuratorApis,
  mockLibrarySyncJobs,
  resetMockCertifications,
  runningLibrarySyncJob,
} from "./fixtures/api-mocks";
import { completeOnboardingViaApi } from "./fixtures/helpers";

test.describe("CA release mocked flows", () => {
  test.beforeEach(async ({ page }) => {
    resetMockCertifications();
    await mockCuratorApis(page);
  });

  test("health endpoint responds and app shell loads", async ({ page, request }) => {
    const health = await request.get("/api/health");
    expect(health.ok()).toBeTruthy();
    const body = await health.json();
    expect(body).toMatchObject({ status: "ok" });

    await page.goto("/");
    await page.getByTestId("composer-input").waitFor();
    await expect(page.getByTestId("workspace-main")).toBeVisible();
  });

  test("config library sync card shows friendly phase label and percent", async ({
    page,
    request,
  }) => {
    await completeOnboardingViaApi(request);
    await mockLibrarySyncJobs(page, [runningLibrarySyncJob()]);

    await page.goto("/admin/sync");
    await page.getByTestId("library-sync-card").waitFor();

    const status = page.getByTestId("library-sync-job-status");
    await expect(status).toBeVisible();
    await expect(status).toContainText("Scanning movies");
    await expect(status).toContainText("18%");
    await expect(status).toContainText("Scanning Plex movies");

    await expect(page.locator("body")).not.toContainText("(Phase 8)");
    await expect(page.locator("body")).not.toContainText("Phase 8");
  });

  test("config maintenance has no phase labels in copy", async ({ page, request }) => {
    await completeOnboardingViaApi(request);
    await page.goto("/admin/overview");
    await page.getByTestId("maintenance-dashboard").waitFor();
    await page.goto("/admin/sync");
    await expect(page.getByTestId("library-sync-card")).toBeVisible();
    await expect(page.locator("body")).not.toContainText("(Phase");
  });
});

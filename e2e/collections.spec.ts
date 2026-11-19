import { expect, test } from "@playwright/test";
import { mockCuratorApis, mockFeatures, resetMockCertifications } from "./fixtures/api-mocks";

test.describe("Collections slash command visibility", () => {
  test.beforeEach(async ({ page }) => {
    resetMockCertifications();
    await mockCuratorApis(page);
    await page.goto("/chat");
    await page.getByTestId("composer-input").waitFor();
  });

  test("hides /collections in /help when plex_collections_enabled is false", async ({ page }) => {
    await mockFeatures(page, { plex_collections_enabled: false });
    await page.reload();
    await page.getByTestId("composer-input").waitFor();

    await page.getByTestId("composer-input").fill("/help");
    await page.getByTestId("send-button").click();

    const assistant = page.getByTestId("chat-message-assistant");
    await expect(assistant).toContainText("/rate");
    await expect(assistant).not.toContainText("/collections");
  });

  test("shows /collections in /help when plex_collections_enabled is true", async ({ page }) => {
    await mockFeatures(page, { plex_collections_enabled: true });
    await page.reload();
    await page.getByTestId("composer-input").waitFor();

    await page.getByTestId("composer-input").fill("/help");
    await page.getByTestId("send-button").click();

    await expect(page.getByTestId("chat-message-assistant")).toContainText("/collections");
  });

  test("/collections explains disabled state when feature flag is off", async ({ page }) => {
    await mockFeatures(page, { plex_collections_enabled: false });
    await page.reload();
    await page.getByTestId("composer-input").waitFor();

    await page.getByTestId("composer-input").fill("/collections");
    await page.getByTestId("send-button").click();

    await expect(page.getByTestId("chat-message-assistant")).toContainText("Plex collections are disabled");
  });
});

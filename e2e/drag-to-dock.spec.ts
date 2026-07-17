import { expect, test } from "@playwright/test";
import {
  mockChatStreamMessage,
  mockCuratorApis,
  mockSetupStatus,
  resetMockCertifications,
} from "./fixtures/api-mocks";

const MOCK_MOVIE = {
  media_type: "movie",
  title: "Blade Runner",
  year: 1982,
  tmdb_id: 78,
  poster_url: "",
  genres: ["Sci-Fi"],
  in_library: false,
};

const MOCK_SHOW = {
  media_type: "show",
  title: "The Wire",
  year: 2002,
  tvdb_id: 79126,
  poster_url: "",
  genres: ["Crime"],
  in_library: false,
};

async function mockMixedTitleCardChat(page: import("@playwright/test").Page) {
  await mockChatStreamMessage(page, () => ({
    id: "assistant-mixed",
    role: "assistant",
    blocks: [
      { type: "text", content: "Here are picks for movies and TV." },
      { type: "title_cards", items: [MOCK_MOVIE, MOCK_SHOW] },
    ],
    created_at: Math.floor(Date.now() / 1000),
    lens_id: "general",
  }));

  await page.route("**/api/actions/propose", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ confirmation_token: "mock-token", action: "add_radarr" }),
    });
  });

  await page.route("**/api/actions/confirm", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, action: "add_radarr" }),
    });
  });
}

async function dragTitleCardToDock(
  page: import("@playwright/test").Page,
  item: typeof MOCK_MOVIE | typeof MOCK_SHOW,
) {
  await page.evaluate((payload) => {
    const dataTransfer = new DataTransfer();
    dataTransfer.setData("application/x-curatorx-title-card", JSON.stringify(payload));
    const dock = document.querySelector('[data-testid="status-dock"]');
    if (!dock) throw new Error("status dock not found");
    dock.dispatchEvent(new DragEvent("dragover", { bubbles: true, dataTransfer }));
    dock.dispatchEvent(new DragEvent("drop", { bubbles: true, dataTransfer }));
  }, item);
}

test.describe("Drag title cards to status dock", () => {
  test.beforeEach(async ({ page }) => {
    resetMockCertifications();
    await mockCuratorApis(page);
    await mockSetupStatus(page, { radarrOk: true, sonarrOk: true });
    await mockMixedTitleCardChat(page);
    const setupResponse = page.waitForResponse(
      (response) => response.url().includes("/api/setup/status") && response.ok(),
    );
    await page.goto("/");
    await setupResponse;
    await page.getByTestId("composer-input").waitFor();
  });

  test("shows drop hint only while dragging a title card", async ({ page }) => {
    await page.getByTestId("composer-input").fill("recommend titles");
    await page.getByTestId("send-button").click();

    await expect(page.getByTestId("status-dock-drop-hint")).toHaveCount(0);

    const movieCard = page.getByTestId("chat-message-assistant").getByTestId("title-card").first();
    await expect(movieCard).toContainText("Blade Runner");

    await page.evaluate(() => {
      const card = document.querySelector('[data-testid="title-card"]');
      if (!card) throw new Error("title card not found");
      const dataTransfer = new DataTransfer();
      dataTransfer.setData("application/x-curatorx-title-card", "{}");
      card.dispatchEvent(new DragEvent("dragstart", { bubbles: true, dataTransfer }));
    });

    const hint = page.getByTestId("status-dock-drop-hint");
    await expect(hint).toBeVisible();
    await expect(hint).toContainText("Radarr or Sonarr");
  });

  test("dragging a movie card onto the dock queues Radarr add", async ({ page }) => {
    await page.getByTestId("composer-input").fill("recommend titles");
    await page.getByTestId("send-button").click();

    const movieCard = page.getByTestId("chat-message-assistant").getByTestId("title-card").first();
    await expect(movieCard).toContainText("Blade Runner");

    // Reveal dock drop target via dragstart, then drop.
    await page.evaluate(() => {
      const card = document.querySelector('[data-testid="title-card"]');
      if (!card) throw new Error("title card not found");
      const dataTransfer = new DataTransfer();
      dataTransfer.setData("application/x-curatorx-title-card", "{}");
      card.dispatchEvent(new DragEvent("dragstart", { bubbles: true, dataTransfer }));
    });
    await expect(page.getByTestId("status-dock")).toBeVisible();
    await dragTitleCardToDock(page, MOCK_MOVIE);

    // Direct concurrent adds skip the tray confirmation banner.
    await expect(page.getByTestId("add-action-feedback")).toContainText('Added "Blade Runner" to Radarr');
  });

  test("dragging a show card onto the dock queues Sonarr add", async ({ page }) => {
    await page.route("**/api/actions/propose", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ confirmation_token: "mock-token", action: "add_sonarr" }),
      });
    });
    await page.route("**/api/actions/confirm", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, action: "add_sonarr" }),
      });
    });

    await page.getByTestId("composer-input").fill("recommend titles");
    await page.getByTestId("send-button").click();

    const showCard = page.getByTestId("chat-message-assistant").getByTestId("title-card").nth(1);
    await expect(showCard).toContainText("The Wire");

    await page.evaluate(() => {
      const card = document.querySelectorAll('[data-testid="title-card"]')[1];
      if (!card) throw new Error("show card not found");
      const dataTransfer = new DataTransfer();
      dataTransfer.setData("application/x-curatorx-title-card", "{}");
      card.dispatchEvent(new DragEvent("dragstart", { bubbles: true, dataTransfer }));
    });
    await expect(page.getByTestId("status-dock")).toBeVisible();
    await dragTitleCardToDock(page, MOCK_SHOW);

    await expect(page.getByTestId("add-action-feedback")).toContainText('Added "The Wire" to Sonarr');
  });
});

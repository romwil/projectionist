import { expect, test } from "@playwright/test";
import { mockCuratorApis, resetMockCertifications } from "./fixtures/api-mocks";

const MOCK_CARDS = [
  {
    media_type: "movie",
    title: "Blade Runner",
    year: 1982,
    tmdb_id: 78,
    poster_url: "",
    genres: ["Sci-Fi", "Thriller"],
    in_library: false,
    recommendation_reason: "Neo-noir classic",
  },
  {
    media_type: "movie",
    title: "Chinatown",
    year: 1974,
    tmdb_id: 829,
    poster_url: "",
    genres: ["Crime", "Drama"],
    in_library: false,
    recommendation_reason: "LA noir essential",
  },
];

async function mockTitleCardChat(page: import("@playwright/test").Page) {
  await page.route("**/api/chat", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    let sessionId = crypto.randomUUID().replace(/-/g, "");
    try {
      const body = route.request().postDataJSON() as { session_id?: string };
      sessionId = body.session_id || sessionId;
    } catch {
      // ignore
    }
    const assistantMessage = {
      id: "assistant-cards",
      role: "assistant",
      blocks: [
        { type: "text", content: "Here are some neo-noir picks for you." },
        { type: "title_cards", items: MOCK_CARDS },
        {
          type: "action_prompt",
          action: "open_viewport",
          payload: { title: "Recommendations", items: MOCK_CARDS },
        },
      ],
      created_at: Math.floor(Date.now() / 1000),
      lens_id: "general",
    };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ session_id: sessionId, message: assistantMessage }),
    });
  });

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
      body: JSON.stringify({ ok: true }),
    });
  });
}

async function sendMockChat(page: import("@playwright/test").Page) {
  await page.getByTestId("composer-input").fill("recommend neo-noir films");
  await page.getByTestId("send-button").click();
  await expect(page.getByTestId("chat-scroll-region")).toBeVisible();
}

test.describe("Title cards in chat", () => {
  test.beforeEach(async ({ page }) => {
    resetMockCertifications();
    await mockCuratorApis(page);
    await mockTitleCardChat(page);
    await page.goto("/");
    await page.getByTestId("composer-input").waitFor();
  });

  test("shows proposed title cards with New badge in chat", async ({ page }) => {
    await sendMockChat(page);

    await expect(page.getByTestId("chat-message-assistant")).toContainText("Blade Runner");
    await expect(page.getByTestId("chat-message-assistant")).toContainText("Chinatown");
    await expect(page.getByTestId("chat-message-assistant").getByText("New").first()).toBeVisible();
  });

  test("expand titles button opens turnstyle overlay with cards", async ({ page }) => {
    await sendMockChat(page);

    await page.getByTestId("expand-title-cards").click();

    const overlay = page.getByTestId("turnstyle-results-overlay");
    await expect(overlay).toBeVisible();
    await expect(overlay).toContainText("Blade Runner");
    await expect(overlay).toContainText("Chinatown");
  });

  test("title card Add button is visible without scrolling", async ({ page }) => {
    await sendMockChat(page);

    const addBtn = page.getByTestId("chat-message-assistant").getByTestId("add-radarr-button").first();
    await expect(addBtn).toBeVisible();
    await expect(addBtn).toContainText("Add to Radarr");

    const box = await addBtn.boundingBox();
    const viewport = page.viewportSize();
    expect(box).not.toBeNull();
    expect(viewport).not.toBeNull();
    expect(box!.y).toBeGreaterThanOrEqual(0);
    expect(box!.y + box!.height).toBeLessThanOrEqual(viewport!.height);
  });

  test("title card Add button is clickable in chat", async ({ page }) => {
    await sendMockChat(page);

    const chatCard = page.getByTestId("chat-message-assistant").getByTestId("title-card").first();
    await expect(chatCard).toContainText("Blade Runner");
    await chatCard.getByTestId("add-radarr-button").click();

    const banner = page.getByTestId("add-action-banner");
    await expect(banner).toBeVisible();
    await expect(banner).toContainText("Blade Runner");
    await expect(banner).toContainText("Radarr");
  });

  test("turnstyle overlay Add button is clickable", async ({ page }) => {
    await sendMockChat(page);
    await page.getByTestId("expand-title-cards").click();

    const overlay = page.getByTestId("turnstyle-results-overlay");
    await expect(overlay).toBeVisible();
    await overlay.getByTestId("add-radarr-button").first().click();

    const banner = page.getByTestId("add-action-banner");
    await expect(banner).toBeVisible();
    await expect(banner).toContainText("Blade Runner");
  });

  test("confirming add shows success feedback and calls propose/confirm APIs", async ({ page }) => {
    const proposeRequests: unknown[] = [];
    const confirmRequests: unknown[] = [];

    await page.route("**/api/actions/propose", async (route) => {
      proposeRequests.push(route.request().postDataJSON());
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ confirmation_token: "mock-token", action: "add_radarr" }),
      });
    });

    await page.route("**/api/actions/confirm", async (route) => {
      confirmRequests.push(route.request().postDataJSON());
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, action: "add_radarr" }),
      });
    });

    await sendMockChat(page);
    await page.getByTestId("chat-message-assistant").getByTestId("add-radarr-button").first().click();

    await expect(page.getByTestId("add-action-banner")).toBeVisible();
    await page.getByTestId("add-action-confirm").click();

    await expect(page.getByTestId("add-action-feedback")).toContainText('Added "Blade Runner" to Radarr');
    expect(proposeRequests).toHaveLength(1);
    expect(confirmRequests).toHaveLength(1);
    expect(proposeRequests[0]).toMatchObject({ action: "add_radarr", tmdb_id: 78, title: "Blade Runner" });
    expect(confirmRequests[0]).toMatchObject({ token: "mock-token", confirmed: true });
  });

  test("add failure shows visible error feedback", async ({ page }) => {
    await page.route("**/api/actions/confirm", async (route) => {
      await route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Radarr is not configured" }),
      });
    });

    await sendMockChat(page);
    await page.getByTestId("chat-message-assistant").getByTestId("add-radarr-button").first().click();
    await page.getByTestId("add-action-confirm").click();

    await expect(page.getByTestId("add-action-feedback")).toContainText("Radarr is not configured");
    await expect(page.getByTestId("add-action-banner")).toBeVisible();
  });

  test("confirm all button adds every title in one batch", async ({ page }) => {
    const proposeRequests: unknown[] = [];
    const confirmRequests: unknown[] = [];

    await page.route("**/api/actions/propose", async (route) => {
      proposeRequests.push(route.request().postDataJSON());
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ confirmation_token: `token-${proposeRequests.length}`, action: "add_radarr" }),
      });
    });

    await page.route("**/api/actions/confirm", async (route) => {
      confirmRequests.push(route.request().postDataJSON());
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, action: "add_radarr" }),
      });
    });

    await sendMockChat(page);
    await page.getByTestId("confirm-all-radarr").click();

    await expect(page.getByTestId("bulk-add-banner")).toHaveCount(0);
    await expect(page.getByTestId("add-action-feedback")).toContainText("Added 2 titles to Radarr");
    expect(proposeRequests).toHaveLength(2);
    expect(confirmRequests).toHaveLength(2);
  });

  test("Why this expands human rationale and hides pipeline labels", async ({ page }) => {
    await page.route("**/api/chat", async (route) => {
      if (route.request().method() !== "POST") {
        await route.continue();
        return;
      }
      let sessionId = crypto.randomUUID().replace(/-/g, "");
      try {
        const body = route.request().postDataJSON() as { session_id?: string };
        sessionId = body.session_id || sessionId;
      } catch {
        // ignore
      }
      const cards = [
        {
          ...MOCK_CARDS[0],
          recommendation_reason: "Neo-noir classic that fits your unwatched streak",
        },
        {
          ...MOCK_CARDS[1],
          recommendation_reason: "TMDB title match",
        },
      ];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: sessionId,
          message: {
            id: "assistant-why",
            role: "assistant",
            blocks: [
              { type: "text", content: "Here are some picks." },
              { type: "title_cards", items: cards },
            ],
            created_at: Math.floor(Date.now() / 1000),
            lens_id: "general",
          },
        }),
      });
    });

    await sendMockChat(page);

    const humanCard = page.getByTestId("chat-message-assistant").getByTestId("title-card").first();
    await expect(humanCard.getByTestId("title-card-why-toggle")).toBeVisible();
    await humanCard.getByTestId("title-card-why-toggle").click();
    await expect(humanCard.getByTestId("title-card-why-detail")).toContainText(
      "Neo-noir classic that fits your unwatched streak",
    );

    const pipelineCard = page.getByTestId("chat-message-assistant").getByTestId("title-card").nth(1);
    await expect(pipelineCard.getByTestId("title-card-why-toggle")).toHaveCount(0);
    await expect(pipelineCard).not.toContainText("TMDB title match");
  });
});

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

const LIBRARY_CARD = {
  media_type: "movie",
  title: "Heat",
  year: 1995,
  tmdb_id: 949,
  rating_key: "plex-949",
  poster_url: "",
  genres: ["Crime", "Drama"],
  in_library: true,
  recommendation_reason: "In your library",
};

function sseDonePayload(sessionId: string, message: Record<string, unknown>, pendingTokens: unknown[] = []) {
  const payload = {
    type: "done",
    session_id: sessionId,
    message,
    pending_tokens: pendingTokens,
  };
  return `event: done\ndata: ${JSON.stringify(payload)}\n\n`;
}

async function mockChatStreamMessage(
  page: import("@playwright/test").Page,
  buildMessage: (sessionId: string) => Record<string, unknown>,
) {
  await page.route("**/api/chat/stream**", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    const url = new URL(route.request().url());
    const sessionId = url.searchParams.get("session_id") || crypto.randomUUID().replace(/-/g, "");
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sseDonePayload(sessionId, buildMessage(sessionId)),
    });
  });
}

async function mockTitleCardChat(page: import("@playwright/test").Page) {
  await mockChatStreamMessage(page, () => ({
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
      body: JSON.stringify({ ok: true }),
    });
  });
}

async function sendMockChat(page: import("@playwright/test").Page) {
  await page.getByTestId("composer-input").fill("recommend neo-noir films");
  await page.getByTestId("send-button").click();
  await expect(page.getByTestId("chat-message-assistant")).toBeVisible();
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

    // Direct concurrent adds skip the tray confirmation banner.
    await expect(page.getByTestId("add-action-feedback")).toContainText('Added "Blade Runner" to Radarr');
  });

  test("turnstyle overlay Add button is clickable", async ({ page }) => {
    await sendMockChat(page);
    await page.getByTestId("expand-title-cards").click();

    const overlay = page.getByTestId("turnstyle-results-overlay");
    await expect(overlay).toBeVisible();
    await overlay.getByTestId("add-radarr-button").first().click();

    await expect(page.getByTestId("add-action-feedback")).toContainText('Added "Blade Runner" to Radarr');
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

    await expect(page.getByTestId("add-action-feedback")).toContainText("Radarr is not configured");
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

  test("title card poster links to detail page", async ({ page }) => {
    await page.route("**/api/title/movie/78/neighbors**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [], total: 0 }),
      });
    });
    await page.route("**/api/title/movie/78**", async (route) => {
      if (route.request().url().includes("/neighbors")) {
        await route.continue();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          media_type: "movie",
          title: "Blade Runner",
          year: 1982,
          tmdb_id: 78,
          overview: "A blade runner must pursue replicants.",
          trailer_youtube_key: "eogpIG53Cis",
          in_library: false,
          recommendation_reason: "Neo-noir classic with rain-slicked neon.",
          runtime_minutes: 117,
          genres: ["Sci-Fi", "Thriller"],
          directors: ["Ridley Scott"],
        }),
      });
    });

    await sendMockChat(page);

    const card = page.getByTestId("chat-message-assistant").getByTestId("title-card").first();
    await expect(card.getByTestId("title-card-detail-link")).toHaveAttribute("href", "/title/movie/78");
    await expect(page.getByTestId("agent-avatar").first()).toBeVisible();
    await card.getByTestId("title-card-title-link").click();
    await expect(page).toHaveURL(/\/title\/movie\/78$/);
    await expect(page.getByTestId("title-detail-page")).toContainText("Blade Runner");
    await expect(page.getByTestId("title-detail-hero")).toBeVisible();
    await expect(page.getByTestId("title-why-card")).toBeVisible();
    await page.getByTestId("watch-trailer-button").click();
    await expect(page.getByTestId("trailer-modal")).toBeVisible();
  });

  test("turnstyle cards also link to detail page", async ({ page }) => {
    await sendMockChat(page);
    await page.getByTestId("expand-title-cards").click();

    const overlay = page.getByTestId("turnstyle-results-overlay");
    await expect(overlay.getByTestId("title-card-detail-link").first()).toHaveAttribute(
      "href",
      "/title/movie/78",
    );
  });

  test("Watch on Plex appears only for in-library titles with rating_key", async ({ page }) => {
    await mockChatStreamMessage(page, () => ({
      id: "assistant-library",
      role: "assistant",
      blocks: [
        { type: "text", content: "From your library." },
        { type: "title_cards", items: [LIBRARY_CARD, MOCK_CARDS[0]] },
      ],
      created_at: Math.floor(Date.now() / 1000),
      lens_id: "general",
    }));

    await sendMockChat(page);

    const libraryCard = page.getByTestId("chat-message-assistant").getByTestId("title-card").first();
    await expect(libraryCard).toContainText("Heat");
    const plexLink = libraryCard.getByTestId("watch-on-plex-button");
    await expect(plexLink).toBeVisible();
    await expect(plexLink).toHaveAttribute(
      "href",
      "https://app.plex.tv/desktop/#!/server/mock-plex-machine/details?key=%2Flibrary%2Fmetadata%2Fplex-949",
    );

    const discoveryCard = page.getByTestId("chat-message-assistant").getByTestId("title-card").nth(1);
    await expect(discoveryCard.getByTestId("watch-on-plex-button")).toHaveCount(0);
    await expect(discoveryCard.getByTestId("add-radarr-button")).toBeVisible();
  });

  test("Why this expands human rationale and hides pipeline labels", async ({ page }) => {
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
    await mockChatStreamMessage(page, () => ({
      id: "assistant-why",
      role: "assistant",
      blocks: [
        { type: "text", content: "Here are some picks." },
        { type: "title_cards", items: cards },
      ],
      created_at: Math.floor(Date.now() / 1000),
      lens_id: "general",
    }));

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

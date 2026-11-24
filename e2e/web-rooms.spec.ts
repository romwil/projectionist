/**
 * Rooms, Play in…, and the live-channel remote.
 * The room list is names. A pending join does not reveal the film.
 */
import { expect, test } from "@playwright/test";
import { mockCuratorApis, resetMockCertifications } from "./fixtures/api-mocks";

const DETAIL = {
  media_type: "movie",
  title: "Blade Runner",
  year: 1982,
  tmdb_id: 78,
  overview: "A blade runner must pursue replicants.",
  in_library: true,
  rating_key: "plex-78",
  runtime_minutes: 117,
};

test.describe("Web rooms", () => {
  test.beforeEach(async ({ page }) => {
    resetMockCertifications();
    await mockCuratorApis(page);
    await page.route("**/api/features", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          features: { multi_user_enabled: false, llm_configured: true },
          capabilities: {
            rooms: 1,
            session_object: 1,
            shared_sessions: 1,
            session_join: 1,
          },
          auth_methods: [],
          auth: { mode: "disabled", plex_login_enabled: true },
        }),
      });
    });
    await page.route("**/api/rooms", async (route) => {
      if (route.request().method() !== "GET") {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          rooms: [
            {
              id: "room-1",
              name: "Living Room",
              kind: "tv",
              title: "Blade Runner",
              rating_key: "plex-78",
            },
          ],
        }),
      });
    });
    await page.route("**/api/rooms/room-1/join", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "pending", request_id: "ask-1" }),
      });
    });
    await page.route("**/api/title/movie/78/neighbors**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [], total: 0 }),
      });
    });
    await page.route("**/api/title/movie/78**", async (route) => {
      if (route.request().url().includes("/neighbors")) {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(DETAIL),
      });
    });
  });

  test("lists screen names and keeps a pending join untitled", async ({
    page,
  }) => {
    await page.goto("/settings/rooms");
    await expect(page.getByTestId("room-name-room-1")).toHaveText(
      "Living Room",
    );
    await expect(page.getByTestId("rooms-page")).not.toContainText(
      "Blade Runner",
    );
    await expect(page.getByTestId("rooms-page")).not.toContainText("plex-78");
    await page.getByTestId("room-join-room-1").click();
    await expect(page.getByTestId("rooms-notice")).toContainText(
      "Nothing about the film",
    );
    await expect(page.getByTestId("rooms-page")).not.toContainText(
      "Blade Runner",
    );
  });

  test("Play in… starts the film on the chosen screen", async ({ page }) => {
    await page.route("**/api/sessions", async (route) => {
      const body = route.request().postDataJSON() as {
        screen_id?: string;
        rating_key?: string;
      };
      expect(body.screen_id).toBe("room-1");
      expect(body.rating_key).toBe("plex-78");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "sess-1",
          owner_id: "owner-1",
          screen_id: "room-1",
          rating_key: "plex-78",
          position_ms: 0,
          state: "playing",
          level: "off",
        }),
      });
    });
    await page.route("**/api/sessions/sess-1", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "sess-1",
          owner_id: "owner-1",
          position_ms: 0,
          state: "playing",
          level: "off",
        }),
      });
    });
    await page.routeWebSocket("**/api/sessions/sess-1/live", () => {});

    await page.goto("/title/movie/78");
    await expect(page.getByTestId("title-detail-play")).toBeVisible();
    await page.getByTestId("play-in-button").click();
    await page.getByTestId("play-in-room-1").click();
    await expect(page).toHaveURL(/\/remote\/sess-1/);
    await expect(page.getByTestId("session-remote-room")).toHaveText(
      "Living Room",
    );
  });

  test("the remote sends pause on the live channel", async ({ page }) => {
    await page.route("**/api/sessions/sess-1", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "sess-1",
          owner_id: "owner-1",
          position_ms: 5000,
          state: "playing",
          level: "off",
        }),
      });
    });
    await page.route("**/api/auth/me", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          authenticated: true,
          user: { id: "owner-1", role: "owner" },
        }),
      });
    });
    await page.routeWebSocket("**/api/sessions/sess-1/live", (socket) => {
      socket.send(
        JSON.stringify({
          type: "state",
          server_time_ms: Date.now(),
          position_ms: 5000,
          state: "playing",
          level: "off",
        }),
      );
      socket.onMessage((message) => {
        const body = JSON.parse(String(message)) as {
          command?: string;
          s?: number;
        };
        if (body.command === "pause") {
          socket.send(
            JSON.stringify({
              type: "state",
              server_time_ms: Date.now(),
              position_ms: 5000,
              state: "paused",
              level: "off",
            }),
          );
        }
        if (body.command === "skip") {
          socket.send(
            JSON.stringify({
              type: "position",
              server_time_ms: Date.now(),
              position_ms: 5000 + Number(body.s || 0) * 1000,
              state: "playing",
              level: "off",
            }),
          );
        }
      });
    });

    await page.goto("/remote/sess-1");
    await expect(page.getByTestId("session-remote-state")).toHaveText(
      "playing",
    );
    await page.getByTestId("session-remote-pause").click();
    await expect(page.getByTestId("session-remote-state")).toHaveText("paused");
    await expect(page.getByTestId("session-remote-position")).toHaveText(
      "0:05",
    );
  });
});

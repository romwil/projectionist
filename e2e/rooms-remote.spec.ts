/**
 * Rooms, Play in…, and the live-channel remote. Mocked e2e on :8799.
 * The room list is names only. A pending join does not name the film.
 */
import { expect, test } from "@playwright/test";
import {
  mockAuthUser,
  mockCuratorApis,
  mockFeatures,
  mockSetupStatus,
  resetMockCertifications,
} from "./fixtures/api-mocks";

const ROOM = "11111111-1111-1111-1111-111111111111";

const SESSION = {
  id: "sess-1",
  owner_id: "owner-1",
  screen_id: ROOM,
  rating_key: "plex-78",
  position_ms: 15000,
  state: "playing",
  level: "off",
  guests: [] as string[],
  guests_may_remote: false,
  held_for_ceiling: false,
};

const DETAIL = {
  media_type: "movie",
  title: "Blade Runner",
  year: 1982,
  tmdb_id: 78,
  overview: "A blade runner must pursue replicants.",
  in_library: true,
  rating_key: "plex-78",
  genres: ["Sci-Fi"],
};

test.describe("Rooms and the remote", () => {
  test.beforeEach(async ({ page }) => {
    resetMockCertifications();
    await mockCuratorApis(page);
    await mockSetupStatus(page, { onboardingComplete: true, radarrOk: true, sonarrOk: true });
    await mockFeatures(page, { multi_user_enabled: true, llm_configured: true });
    await page.route("**/api/features", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          features: { multi_user_enabled: true, llm_configured: true },
          capabilities: {
            rooms: 1,
            session_object: 1,
            shared_sessions: 1,
            session_join: 1,
          },
          auth_methods: ["plex"],
        }),
      });
    });
    await mockAuthUser(page, {
      id: "owner-1",
      display_name: "Household Owner",
      role: "owner",
      default_page: "explore",
    });
    await page.route("**/api/rooms", async (route) => {
      if (route.request().method() !== "GET") {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ rooms: [{ id: ROOM, name: "Living Room", kind: "tv" }] }),
      });
    });
    await page.route(`**/api/rooms/${ROOM}/join`, async (route) => {
      const body = route.request().postDataJSON() as { code?: string };
      if (String(body?.code || "") === "abcd1234") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ ...SESSION, status: "joined" }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "pending", request_id: "req-1" }),
      });
    });
    await page.route("**/api/sessions", async (route) => {
      if (route.request().method() !== "POST") {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(SESSION),
      });
    });
    await page.route("**/api/sessions/sess-1", async (route) => {
      if (route.request().url().includes("/live")) {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(SESSION),
      });
    });
    await page.route("**/api/sessions/sess-1/code", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ code: "abcd1234" }),
      });
    });
    await page.route("**/api/sessions/sess-1/join-requests", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ requests: [{ id: "ask-1", display_name: "Sam" }] }),
      });
    });
    await page.routeWebSocket("**/api/sessions/sess-1/live", (socket) => {
      socket.send(
        JSON.stringify({
          type: "state",
          server_time_ms: Date.now(),
          position_ms: 15000,
          state: "playing",
          level: "off",
        }),
      );
      socket.onMessage((message) => {
        const payload = JSON.parse(String(message)) as { command?: string };
        if (payload.command === "pause") {
          socket.send(
            JSON.stringify({
              type: "state",
              server_time_ms: Date.now(),
              position_ms: 15000,
              state: "paused",
              level: "off",
            }),
          );
        }
      });
    });
    await page.route("**/api/title/movie/78**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(DETAIL),
      });
    });
  });

  test("a room is a name, and a join without a code hides the film", async ({ page }) => {
    await page.goto("/settings/rooms");
    await expect(page.getByRole("heading", { name: "Rooms" })).toBeVisible();
    await expect(page.getByTestId(`room-name-${ROOM}`)).toHaveText("Living Room");
    await expect(page.getByTestId("rooms-page")).not.toContainText("plex-78");
    await expect(page.getByTestId("rooms-page")).not.toContainText("Blade Runner");
    await page.getByTestId(`room-join-${ROOM}`).click();
    await expect(page.getByTestId("rooms-notice")).toContainText("Nothing about the film");
    await expect(page.getByTestId("rooms-page")).not.toContainText("plex-78");
  });

  test("the code opens the remote and pause uses the live channel", async ({ page }) => {
    await page.goto("/settings/rooms");
    await page.getByTestId(`room-code-${ROOM}`).fill("abcd1234");
    await page.getByTestId(`room-join-${ROOM}`).click();
    await expect(page.getByTestId("session-remote")).toBeVisible();
    await expect(page.getByTestId("session-remote-room")).toHaveText("Living Room");
    await expect(page.getByTestId("session-remote-code")).toHaveText("Code abcd1234");
    await expect(page.getByTestId("session-remote")).not.toContainText("plex-78");
    await expect(page.getByTestId("join-request-ask-1")).toContainText("Sam wants to join.");
    await expect(page.getByTestId("session-remote-state")).toHaveText("playing");
    await page.getByTestId("session-remote-pause").click();
    await expect(page.getByTestId("session-remote-state")).toHaveText("paused");
  });

  test("Play in… starts a session on the chosen screen", async ({ page }) => {
    await page.goto("/title/movie/78");
    await expect(page.getByTestId("play-in-button")).toBeVisible();
    await page.getByTestId("play-in-button").click();
    await page.getByTestId(`play-in-${ROOM}`).click();
    await expect(page).toHaveURL(/\/remote\/sess-1$/);
    await expect(page.getByTestId("session-remote-room")).toHaveText("Living Room");
  });
});

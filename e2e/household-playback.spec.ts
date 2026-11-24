/**
 * Household playback lives in Admin. Profile keeps personal prefs.
 * Mocked e2e on :8799. Owner sees the controls; a member does not.
 */
import { expect, test } from "@playwright/test";
import { mockAuthUser, mockCuratorApis, mockFeatures, mockSetupStatus, resetMockCertifications } from "./fixtures/api-mocks";

async function mockHouseholdPlaybackApis(page: import("@playwright/test").Page) {
  await page.route("**/api/playback/playability**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        running: false,
        profiles: [],
        message: "No playability report yet.",
      }),
    });
  });
  await page.route("**/api/playback/copies**", async (route) => {
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON() as { output_dir?: string; budget_gib?: number };
      if (String(body.output_dir || "").includes("<") || String(body.output_dir || "").includes("..")) {
        await route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({ detail: "That folder is not allowed." }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          output_dir: body.output_dir || "",
          budget_bytes: Math.round(Number(body.budget_gib || 200) * 1024 * 1024 * 1024),
          used_bytes: 0,
          queue: [],
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        output_dir: "",
        budget_bytes: 200 * 1024 * 1024 * 1024,
        used_bytes: 0,
        queue: [],
      }),
    });
  });
  await page.route("**/api/playback/engine-setting", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ play_through_projectionist: true }),
    });
  });
  await page.route("**/api/network/public-base-url", async (route) => {
    const body = route.request().postDataJSON() as { public_base_url?: string };
    const value = String(body.public_base_url || "");
    if (value.includes(" ") || value.includes("<") || value.includes("?")) {
      await route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify({ detail: "That address is not an origin." }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ public_base_url: value }),
    });
  });
  await page.route("**/api/engagement/summary", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ badges: [], challenges: [] }),
    });
  });
}

test.describe("Household playback", () => {
  test.beforeEach(async ({ page }) => {
    resetMockCertifications();
    await mockCuratorApis(page);
    await mockSetupStatus(page, { onboardingComplete: true, radarrOk: true, sonarrOk: true });
    await mockHouseholdPlaybackApis(page);
  });

  test("owner sees household controls in admin and only personal prefs on Profile", async ({ page }) => {
    await mockFeatures(page, {
      multi_user_enabled: true,
      play_through_projectionist: false,
    });
    await page.route("**/api/features", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          features: {
            multi_user_enabled: true,
            play_through_projectionist: false,
            llm_configured: true,
          },
          addresses: { away: "" },
          auth_methods: ["plex"],
          auth: { mode: "plex", plex_login_enabled: true },
        }),
      });
    });
    await mockAuthUser(page, {
      id: "owner-1",
      display_name: "Household Owner",
      role: "owner",
      default_page: "explore",
    });

    await page.goto("/admin/playback");
    await expect(page.getByTestId("household-playback")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Playback", level: 2 })).toBeVisible();
    await expect(page.getByTestId("admin-nav-heading-members")).toHaveText("Household");
    await expect(page.getByTestId("admin-nav-playback")).toBeVisible();
    await expect(page.getByTestId("play-through-projectionist")).toBeVisible();
    await expect(page.getByTestId("play-through-household-note")).toHaveText(
      "This affects everyone in the household.",
    );
    await expect(page.getByTestId("away-address")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Library playability", level: 4 })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Copies ahead of time", level: 4 })).toBeVisible();
    await expect(page.getByLabel("Output folder")).toBeVisible();
    await expect(page.getByLabel("Disk budget (GiB)")).toBeVisible();

    await page.getByLabel("Output folder").fill("../<script>");
    await page.getByTestId("copies-save").click();
    await expect(page.getByTestId("copies-error")).toHaveText("That folder is not allowed.");

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByTestId("play-through-household-note")).toBeVisible();
    await page.setViewportSize({ width: 1280, height: 800 });

    await page.goto("/settings/profile");
    await expect(page.getByTestId("settings-profile")).toBeVisible();
    await expect(page.getByTestId("pause-when-backgrounded")).toBeVisible();
    await expect(page.getByTestId("font-size-fieldset")).toBeVisible();
    await expect(page.getByTestId("default-page-fieldset")).toBeVisible();
    await expect(page.getByTestId("play-through-projectionist")).toHaveCount(0);
    await expect(page.getByTestId("away-address")).toHaveCount(0);
    await expect(page.getByTestId("playability-report")).toHaveCount(0);
    await expect(page.getByTestId("copies-ahead")).toHaveCount(0);
  });

  test("an old Profile playback anchor lands on Household → Playback", async ({ page }) => {
    await mockFeatures(page, { multi_user_enabled: true });
    await page.route("**/api/features", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          features: { multi_user_enabled: true, llm_configured: true },
          addresses: { away: "https://films.example" },
          auth_methods: ["plex"],
          auth: { mode: "plex", plex_login_enabled: true },
        }),
      });
    });
    await mockAuthUser(page, {
      id: "owner-1",
      display_name: "Household Owner",
      role: "owner",
    });

    await page.goto("/settings/profile#playback");
    await expect(page).toHaveURL(/\/admin\/playback$/);
    await expect(page.getByTestId("household-playback")).toBeVisible();
    await expect(page.getByTestId("play-through-household-note")).toBeVisible();

    await page.goto("/settings/playback");
    await expect(page).toHaveURL(/\/admin\/playback$/);
  });

  test("a member does not see household playback controls", async ({ page }) => {
    await mockFeatures(page, { multi_user_enabled: true });
    await page.route("**/api/features", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          features: { multi_user_enabled: true, llm_configured: true },
          addresses: { away: "https://films.example" },
          auth_methods: ["plex"],
          auth: { mode: "plex", plex_login_enabled: true },
        }),
      });
    });
    await mockAuthUser(page, {
      id: "member-1",
      display_name: "Household Member",
      role: "member",
      default_page: "explore",
    });

    await page.goto("/settings/profile");
    await expect(page.getByTestId("settings-profile")).toBeVisible();
    await expect(page.getByTestId("pause-when-backgrounded")).toBeVisible();
    await expect(page.getByTestId("font-size-fieldset")).toBeVisible();
    await expect(page.getByTestId("default-page-fieldset")).toBeVisible();
    await expect(page.getByTestId("play-through-projectionist")).toHaveCount(0);
    await expect(page.getByTestId("away-address")).toHaveCount(0);
    await expect(page.getByTestId("playability-report")).toHaveCount(0);
    await expect(page.getByTestId("copies-ahead")).toHaveCount(0);
    await expect(page.getByTestId("household-playback")).toHaveCount(0);

    await page.goto("/admin/playback");
    await expect(page).toHaveURL(/\/settings/);
    await expect(page.getByTestId("household-playback")).toHaveCount(0);
    await expect(page.getByTestId("play-through-projectionist")).toHaveCount(0);

    await page.goto("/settings/profile#playback");
    await expect(page.getByTestId("household-playback")).toHaveCount(0);
    await expect(page.getByTestId("play-through-projectionist")).toHaveCount(0);
  });
});

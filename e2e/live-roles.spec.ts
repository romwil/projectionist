/**
 * Full multi-role UI coverage against the QA sidecar (auth ON).
 * Skipped unless CURATORX_E2E_QA_ROLES=1 and e2e/.auth/*.json exist
 * (generate via e2e/auth.setup.ts after scripts/seed-qa-roles.sh).
 *
 *   set -a && source .env.qa && set +a
 *   CURATORX_E2E_QA_ROLES=1 E2E_BASE_URL=http://10.10.1.202:8790 \
 *     npm run test:e2e:qa-roles
 *
 * Role matrix (primaryNav + shells):
 *   Owner  — Search, Chat, Explore, Inbox, Admin, My Journey, Settings
 *   Member — Search, Chat, Explore, Inbox, My Journey, Settings (no Admin)
 *   Youth  — same as member; youth shell; Ask/Browse labels; no Admin
 *   Guest  — Search, Chat, Explore only (guest shell)
 *   Tour   — public /tour; Help/Privacy; chat/explore redirect to login
 */

import { expect, type Browser, type BrowserContext, type Page, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import {
  qaBaseURL,
  rolesEnabled,
  storageStatePath,
  type QaRole,
} from "./fixtures/auth-roles";

const AUTH_DIR = path.join(process.cwd(), "e2e", ".auth");

function hasState(role: QaRole): boolean {
  return fs.existsSync(storageStatePath(role));
}

function hasGuestTourState(): boolean {
  return fs.existsSync(path.join(AUTH_DIR, "guest-tour.json"));
}

async function openWithState(
  browser: Browser,
  storageState: string | undefined,
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({
    baseURL: qaBaseURL(),
    storageState,
  });
  const page = await context.newPage();
  return { context, page };
}

async function assertNotLogin(page: Page): Promise<void> {
  await expect(page.getByTestId("login-page")).toHaveCount(0, { timeout: 30_000 });
}

/** Assert primary topbar peers match the role matrix. */
async function expectTopbarNav(
  page: Page,
  {
    expectAdmin,
    expectMemberPeers,
    expectGuestOnly,
  }: {
    expectAdmin: boolean;
    expectMemberPeers: boolean;
    expectGuestOnly: boolean;
  },
): Promise<void> {
  const topbar = page.getByTestId("primary-topbar");
  await expect(topbar).toBeVisible({ timeout: 30_000 });

  await expect(page.getByTestId("topbar-search-link")).toBeVisible();
  await expect(page.getByTestId("topbar-chat-link")).toBeVisible();
  await expect(page.getByTestId("topbar-explore-link")).toBeVisible();

  if (expectGuestOnly) {
    await expect(page.getByTestId("topbar-inbox-button")).toHaveCount(0);
    await expect(page.getByTestId("topbar-my-journey-link")).toHaveCount(0);
    await expect(page.getByTestId("topbar-settings-link")).toHaveCount(0);
    await expect(page.getByTestId("topbar-admin-link")).toHaveCount(0);
    return;
  }

  if (expectMemberPeers) {
    await expect(page.getByTestId("topbar-inbox-button")).toBeVisible();
    await expect(page.getByTestId("topbar-my-journey-link")).toBeVisible();
    await expect(page.getByTestId("topbar-settings-link")).toBeVisible();
  }

  if (expectAdmin) {
    await expect(page.getByTestId("topbar-admin-link")).toBeVisible();
  } else {
    await expect(page.getByTestId("topbar-admin-link")).toHaveCount(0);
  }
}

/** Cheap light/dark cycle on shells that expose the topbar theme control. */
async function toggleThemeOnce(page: Page): Promise<void> {
  const toggle = page.getByTestId("topbar-theme-toggle");
  if ((await toggle.count()) === 0) return;
  const before = await page.locator("html").getAttribute("data-theme");
  await toggle.click();
  await expect(page.locator("html")).not.toHaveAttribute("data-theme", before || "__none__");
  // Restore preference so later specs aren't stuck on an unexpected theme.
  await toggle.click();
}

async function expectHelpPrivacy(page: Page, { ownerHelp }: { ownerHelp: boolean }): Promise<void> {
  await page.goto("/help");
  await expect(page.getByTestId("help-page")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("help-content")).toBeVisible();
  if (ownerHelp) {
    await expect(page.getByTestId("help-jump-owners")).toBeVisible();
  } else {
    await expect(page.getByTestId("help-jump-owners")).toHaveCount(0);
  }

  await page.goto("/privacy");
  await expect(page.getByTestId("privacy-page")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("privacy-content")).toBeVisible();
}

test.describe("QA multi-role live UI", () => {
  test.beforeEach(() => {
    test.skip(!rolesEnabled(), "Set CURATORX_E2E_QA_ROLES=1 for multi-role live QA");
  });

  test.describe("Guest tour (public, no login)", () => {
    test("lands on /tour and can open Help / Privacy", async ({ browser }) => {
      const { context, page } = await openWithState(
        browser,
        hasGuestTourState() ? path.join(AUTH_DIR, "guest-tour.json") : undefined,
      );
      try {
        const health = await page.request.get("/api/health");
        expect(health.ok()).toBeTruthy();

        await page.goto("/tour");
        await expect(page.getByTestId("guest-tour-page")).toBeVisible({ timeout: 30_000 });
        // Grid or empty copy — either is a valid tour surface.
        const tourBody = page.getByTestId("guest-tour-grid").or(page.getByTestId("guest-tour-empty"));
        await expect(tourBody.first()).toBeVisible({ timeout: 30_000 });

        await expectHelpPrivacy(page, { ownerHelp: false });
      } finally {
        await context.close();
      }
    });

    test("chat and explore redirect to login when unauthenticated", async ({ browser }) => {
      const { context, page } = await openWithState(browser, undefined);
      try {
        await page.goto("/chat");
        await expect(page.getByTestId("login-page")).toBeVisible({ timeout: 30_000 });

        await page.goto("/explore");
        await expect(page.getByTestId("login-page")).toBeVisible({ timeout: 30_000 });

        await page.goto("/admin");
        await expect(page.getByTestId("login-page")).toBeVisible({ timeout: 30_000 });
      } finally {
        await context.close();
      }
    });
  });

  test.describe("Owner", () => {
    test.beforeEach(({ }, testInfo) => {
      testInfo.skip(!hasState("owner"), `Missing ${storageStatePath("owner")} — run auth.setup first`);
    });

    test("full chrome: chat, explore, search, inbox, journey, settings, admin", async ({
      browser,
    }) => {
      const { context, page } = await openWithState(browser, storageStatePath("owner"));
      try {
        await page.goto("/chat");
        await assertNotLogin(page);
        await expect(page.getByTestId("workspace-main")).toBeVisible({ timeout: 30_000 });
        await expect(page.getByTestId("composer-input")).toBeVisible();
        await expect(page.locator("[data-shell]").first()).not.toHaveAttribute("data-shell", "youth");
        await expect(page.locator("[data-shell]").first()).not.toHaveAttribute("data-shell", "guest");
        await expectTopbarNav(page, {
          expectAdmin: true,
          expectMemberPeers: true,
          expectGuestOnly: false,
        });
        await toggleThemeOnce(page);

        const me = await page.request.get("/api/auth/me");
        expect(me.ok()).toBeTruthy();
        const body = await me.json();
        expect(body.user?.role).toBe("owner");

        await page.goto("/explore");
        await expect(page.getByTestId("explore-page")).toBeVisible({ timeout: 30_000 });
        await expect(page.getByTestId("explore-hub-links")).toBeVisible();

        await page.goto("/search");
        await expect(page.getByTestId("search-page")).toBeVisible({ timeout: 30_000 });

        await page.goto("/inbox");
        await expect(page.getByTestId("inbox-page")).toBeVisible({ timeout: 30_000 });

        await page.goto("/my-journey");
        await expect(page.getByTestId("my-journey-page")).toBeVisible({ timeout: 30_000 });
        await expect(page.getByTestId("journey-hero")).toBeVisible();

        await page.goto("/settings");
        await expect(page.getByTestId("settings-layout")).toBeVisible({ timeout: 30_000 });
        await expect(page.getByTestId("settings-nav-profile")).toBeVisible();

        await page.goto("/admin");
        await expect(page.getByTestId("admin-layout")).toBeVisible({ timeout: 30_000 });
        await expect(page.getByTestId("admin-rail")).toBeVisible();
        await expect(page.getByTestId("admin-nav-overview")).toBeVisible();

        await expectHelpPrivacy(page, { ownerHelp: true });
      } finally {
        await context.close();
      }
    });
  });

  test.describe("Member", () => {
    test.beforeEach(({ }, testInfo) => {
      testInfo.skip(!hasState("member"), `Missing ${storageStatePath("member")} — run auth.setup first`);
    });

    test("member peers without Admin; admin URL redirects away", async ({ browser }) => {
      const { context, page } = await openWithState(browser, storageStatePath("member"));
      try {
        await page.goto("/chat");
        await assertNotLogin(page);
        await expect(page.getByTestId("workspace-main")).toBeVisible({ timeout: 30_000 });
        await expect(page.getByTestId("composer-input")).toBeVisible();
        await expectTopbarNav(page, {
          expectAdmin: false,
          expectMemberPeers: true,
          expectGuestOnly: false,
        });
        await toggleThemeOnce(page);

        const me = await page.request.get("/api/auth/me");
        expect(me.ok()).toBeTruthy();
        expect((await me.json()).user?.role).toBe("member");

        await page.goto("/explore");
        await expect(page.getByTestId("explore-page")).toBeVisible({ timeout: 30_000 });

        await page.goto("/search");
        await expect(page.getByTestId("search-page")).toBeVisible({ timeout: 30_000 });

        await page.goto("/inbox");
        await expect(page.getByTestId("inbox-page")).toBeVisible({ timeout: 30_000 });

        await page.goto("/my-journey");
        await expect(page.getByTestId("my-journey-page")).toBeVisible({ timeout: 30_000 });

        await page.goto("/settings");
        await expect(page.getByTestId("settings-layout")).toBeVisible({ timeout: 30_000 });
        // Owner-only Admin link in settings rail footer must be absent.
        await expect(page.locator(".settings-rail-meta-link", { hasText: "Admin" })).toHaveCount(0);

        await page.goto("/admin");
        await expect(page.getByTestId("admin-layout")).toHaveCount(0, { timeout: 30_000 });
        await expect(page.getByTestId("settings-layout").or(page.getByTestId("login-page"))).toBeVisible();

        await expectHelpPrivacy(page, { ownerHelp: false });
      } finally {
        await context.close();
      }
    });
  });

  test.describe("Youth", () => {
    test.beforeEach(({ }, testInfo) => {
      testInfo.skip(!hasState("youth"), `Missing ${storageStatePath("youth")} — run auth.setup first`);
    });

    test("youth shell, Ask/Browse labels, gated peers, no Admin", async ({ browser }) => {
      const { context, page } = await openWithState(browser, storageStatePath("youth"));
      try {
        await page.goto("/chat");
        await assertNotLogin(page);
        await expect(page.getByTestId("workspace-main")).toBeVisible({ timeout: 30_000 });
        await expect(page.locator(".youth-shell, [data-shell='youth']").first()).toBeVisible();
        await expect(page.getByTestId("composer-input")).toBeVisible();

        // Youth labels on chat/explore peers.
        await expect(page.getByTestId("topbar-chat-link")).toContainText(/Ask/i);
        await expect(page.getByTestId("topbar-explore-link")).toContainText(/Browse/i);

        await expectTopbarNav(page, {
          expectAdmin: false,
          expectMemberPeers: true,
          expectGuestOnly: false,
        });
        await toggleThemeOnce(page);

        const me = await page.request.get("/api/auth/me");
        expect(me.ok()).toBeTruthy();
        const body = await me.json();
        expect(Boolean(body.user?.is_youth)).toBeTruthy();

        await page.goto("/explore");
        await expect(page.getByTestId("explore-page")).toBeVisible({ timeout: 30_000 });

        await page.goto("/search");
        await expect(page.getByTestId("search-page")).toBeVisible({ timeout: 30_000 });

        await page.goto("/inbox");
        await expect(page.getByTestId("inbox-page")).toBeVisible({ timeout: 30_000 });

        await page.goto("/my-journey");
        await expect(page.getByTestId("my-journey-page")).toBeVisible({ timeout: 30_000 });

        await page.goto("/settings/profile");
        await expect(page.getByTestId("settings-layout")).toBeVisible({ timeout: 30_000 });
        await expect(page.getByTestId("youth-mode-badge")).toBeVisible({ timeout: 30_000 });

        await page.goto("/admin");
        await expect(page.getByTestId("admin-layout")).toHaveCount(0, { timeout: 30_000 });

        await expectHelpPrivacy(page, { ownerHelp: false });
      } finally {
        await context.close();
      }
    });
  });

  test.describe("Guest role (logged-in)", () => {
    test.beforeEach(({ }, testInfo) => {
      testInfo.skip(!hasState("guest"), `Missing ${storageStatePath("guest")} — run auth.setup first`);
    });

    test("guest shell: Search/Chat/Explore only; admin/settings peers hidden", async ({
      browser,
    }) => {
      const { context, page } = await openWithState(browser, storageStatePath("guest"));
      try {
        await page.goto("/chat");
        await assertNotLogin(page);
        await expect(page.getByTestId("workspace-main")).toBeVisible({ timeout: 30_000 });
        await expect(page.locator(".guest-shell, [data-shell='guest']").first()).toBeVisible();
        await expect(page.getByTestId("composer-input")).toBeVisible();

        await expect(page.getByTestId("topbar-chat-link")).toContainText(/Ask/i);
        await expect(page.getByTestId("topbar-explore-link")).toContainText(/Browse/i);

        await expectTopbarNav(page, {
          expectAdmin: false,
          expectMemberPeers: false,
          expectGuestOnly: true,
        });
        await toggleThemeOnce(page);

        const me = await page.request.get("/api/auth/me");
        expect(me.ok()).toBeTruthy();
        expect((await me.json()).user?.role).toBe("guest");

        await page.goto("/explore");
        await expect(page.getByTestId("explore-page")).toBeVisible({ timeout: 30_000 });

        await page.goto("/search");
        await expect(page.getByTestId("search-page")).toBeVisible({ timeout: 30_000 });

        // Direct Admin must not expose the owner rail.
        await page.goto("/admin");
        await expect(page.getByTestId("admin-layout")).toHaveCount(0, { timeout: 30_000 });

        await expectHelpPrivacy(page, { ownerHelp: false });
      } finally {
        await context.close();
      }
    });
  });
});

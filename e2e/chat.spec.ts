import { expect, test } from "@playwright/test";
import { mockChatFailure, mockCuratorApis, resetMockCertifications } from "./fixtures/api-mocks";

test.describe("Chat workspace", () => {
  test.beforeEach(async ({ page }) => {
    resetMockCertifications();
    await mockCuratorApis(page);
    await page.goto("/");
    await page.getByTestId("composer-input").waitFor();
  });

  test("loads single workspace with composer and chat region", async ({ page }) => {
    await expect(page.getByTestId("workspace-main")).toBeVisible();
    await expect(page.getByTestId("chat-scroll-region")).toBeVisible();
    await expect(page.getByTestId("composer-input")).toBeVisible();
    await expect(page.getByTestId("send-button")).toBeVisible();
    await expect(page.getByTestId("thread-list")).toBeVisible();
    await expect(page.getByTestId("expand-viewport")).toHaveCount(0);
    await expect(page.getByTestId("immersive-viewport")).toHaveCount(0);
  });

  test("shows ambient context tag in composer", async ({ page }) => {
    await expect(page.getByTestId("ambient-context-tag")).toContainText("⧉");
  });

  test("shows welcome panel on empty thread", async ({ page }) => {
    await expect(page.getByTestId("welcome-panel")).toBeVisible();
    await expect(page.getByTestId("welcome-panel")).toContainText("What should we dig into");
    await expect(page.getByTestId("chat-message-user")).toHaveCount(0);
  });

  test("submit chat records user and assistant messages", async ({ page }) => {
    await page.getByTestId("composer-input").fill("Find neo-noir films");
    await page.getByTestId("send-button").click();
    await expect(page.getByTestId("inline-alert-error")).toHaveCount(0);

    await expect(page.getByTestId("chat-scroll-region")).toBeVisible();
    await expect(page.getByTestId("chat-message-assistant")).toContainText("Echo:");
    await expect(page.getByTestId("chat-message-user")).toContainText("Find neo-noir films");
  });

  test("shows helpful and not helpful buttons on assistant messages", async ({ page }) => {
    await page.getByTestId("composer-input").fill("Rate this reply");
    await page.getByTestId("send-button").click();
    await expect(page.getByTestId("chat-message-assistant")).toBeVisible();

    const assistantMessage = page.getByTestId("chat-message-assistant");
    const reactions = assistantMessage.getByTestId("message-reactions");
    await expect(reactions).toBeVisible();
    await expect(reactions.getByTestId("feedback-helpful")).toBeVisible();
    await expect(reactions.getByTestId("feedback-not-helpful")).toBeVisible();
  });

  test("shows typing indicator while waiting for response", async ({ page }) => {
    await page.route("**/api/chat/stream**", async (route) => {
      if (route.request().method() !== "GET") {
        await route.continue();
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 500));
      const url = new URL(route.request().url());
      const sessionId = url.searchParams.get("session_id") || crypto.randomUUID().replace(/-/g, "");
      const payload = {
        type: "done",
        session_id: sessionId,
        message: {
          id: "assistant-slow",
          role: "assistant",
          blocks: [{ type: "text", content: "Slow reply ready." }],
          created_at: Math.floor(Date.now() / 1000),
          lens_id: "general",
        },
        pending_tokens: [],
      };
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: `event: done\ndata: ${JSON.stringify(payload)}\n\n`,
      });
    });

    await page.getByTestId("composer-input").fill("Slow response test");
    await page.getByTestId("send-button").click();
    await expect(page.getByTestId("typing-indicator")).toBeVisible();
    await expect(page.getByTestId("typing-indicator")).toContainText(/weighing|thinking|Curator/i);
  });

  test("shows visible error when chat API fails", async ({ page }) => {
    await mockChatFailure(page, "LLM provider unavailable");
    await page.reload();
    await page.getByTestId("composer-input").waitFor();

    await page.getByTestId("composer-input").fill("This should fail");
    await page.getByTestId("send-button").click();

    await expect(page.getByTestId("inline-alert-error")).toBeVisible();
    await expect(page.getByTestId("inline-alert-error")).toContainText("LLM provider unavailable");
  });

  test("sidebar rail toggle collapses conversation sidebar", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });

    const sidebar = page.getByTestId("workspace-sidebar");
    await expect(sidebar).not.toHaveClass(/sidebar-collapsed/);

    await page.getByTestId("sidebar-rail-toggle").click();
    await expect(sidebar).toHaveClass(/sidebar-collapsed/);
  });

  test("creates and switches between chat threads", async ({ page }) => {
    await expect(page.getByTestId("thread-list")).toBeVisible();

    const composer = page.getByTestId("composer-input");
    await composer.fill("Thread one message");
    await page.getByTestId("send-button").click();
    await expect(page.getByTestId("chat-message-user")).toContainText("Thread one message");

    await page.getByTestId("new-thread").click();
    await expect(page.getByTestId("chat-message-user")).toHaveCount(0);

    await composer.fill("Thread two message");
    await page.getByTestId("send-button").click();
    await expect(page.getByTestId("chat-message-user")).toContainText("Thread two message");

    const firstThread = page.locator(".thread-item").filter({ hasText: "Thread one message" }).first();
    await firstThread.click();
    await expect(page.getByTestId("chat-message-user")).toContainText("Thread one message");
    await expect(page.getByTestId("chat-message-user")).not.toContainText("Thread two message");
  });

  test("library query API returns honest decade slice metadata", async ({ page }) => {
    const data = await page.evaluate(async () => {
      const res = await fetch("/api/library/query?year_from=1970&year_to=1979&media_type=movie");
      return res.json();
    });
    expect(data.total_matched).toBe(142);
    expect(data.has_more).toBe(true);
    expect(data.items[0].year).toBe(1979);
  });

  test("TV progress API returns show completion metadata", async ({ page }) => {
    const data = await page.evaluate(async () => {
      const res = await fetch("/api/library/tv/progress?group_by=show&in_progress_only=true");
      return res.json();
    });
    expect(data.buckets[0].completion_percent).toBe(50);
    expect(data.buckets[0].show_title).toBe("The Wire");
  });
});

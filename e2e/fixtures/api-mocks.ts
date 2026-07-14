import type { Page, Route } from "@playwright/test";

const MOCK_SECTIONS = [
  { key: "1", title: "Movies", type: "movie" },
  { key: "2", title: "TV Shows", type: "show" },
];

const certifiedServices = new Set<string>();
let forceWizardIncomplete = false;

type MockThread = {
  id: string;
  thread_title: string;
  context_hash: string;
  lens_id: string;
  created_at: number;
  updated_at: number;
  message_count: number;
  preview: string;
};

type MockMessage = {
  id: string;
  role: string;
  blocks: Array<{ type: string; content: string }>;
  created_at: number;
  lens_id: string;
};

const mockThreads = new Map<string, MockThread>();
const mockMessages = new Map<string, MockMessage[]>();
const mockFeedback = new Map<string, Map<string, "helpful" | "not_helpful">>();

function nowSeconds() {
  return Math.floor(Date.now() / 1000);
}

function ensureMockThread(sessionId: string, title = "New conversation") {
  if (!mockThreads.has(sessionId)) {
    const now = nowSeconds();
    mockThreads.set(sessionId, {
      id: sessionId,
      thread_title: title,
      context_hash: "general",
      lens_id: "general",
      created_at: now,
      updated_at: now,
      message_count: 0,
      preview: "",
    });
    mockMessages.set(sessionId, []);
  }
  return mockThreads.get(sessionId)!;
}

export function resetMockCertifications() {
  certifiedServices.clear();
  forceWizardIncomplete = false;
  mockThreads.clear();
  mockMessages.clear();
  mockFeedback.clear();
}

/** Keep Config in the onboarding wizard even when the shared e2e server already completed setup. */
export function setForceWizardIncomplete(value = true) {
  forceWizardIncomplete = value;
}

function certificationEntry(certified: boolean) {
  return {
    certified,
    connection_status: certified ? "verified" : "unverified",
    last_tested_at: certified ? new Date().toISOString() : null,
  };
}

export async function mockCuratorApis(page: Page) {
  if (process.env.E2E_MOCK_APIS === "0") {
    return;
  }

  await page.route("**/api/chat/threads**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();

    if (method === "GET" && url.pathname.endsWith("/feedback")) {
      const parts = url.pathname.split("/");
      const sessionId = parts[parts.length - 2];
      const thread = mockThreads.get(sessionId);
      if (!thread) {
        await route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Thread not found" }),
        });
        return;
      }
      const feedbackMap = mockFeedback.get(sessionId) || new Map();
      const items = [...feedbackMap.entries()].map(([messageId, feedback]) => ({
        id: `feedback-${messageId}`,
        message_id: messageId,
        session_id: sessionId,
        user_id: null,
        feedback,
        excerpt: "",
        created_at: nowSeconds(),
      }));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ session_id: sessionId, items }),
      });
      return;
    }

    if (method === "GET" && url.pathname.endsWith("/messages")) {
      const parts = url.pathname.split("/");
      const sessionId = parts[parts.length - 2];
      const thread = mockThreads.get(sessionId);
      if (!thread) {
        await route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Thread not found" }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: sessionId,
          thread,
          messages: mockMessages.get(sessionId) || [],
        }),
      });
      return;
    }

    if (method === "GET") {
      const threads = [...mockThreads.values()].sort((a, b) => b.updated_at - a.updated_at);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(threads),
      });
      return;
    }

    if (method === "POST") {
      let title = "New conversation";
      try {
        const body = request.postDataJSON() as { thread_title?: string };
        title = body.thread_title || title;
      } catch {
        // ignore malformed bodies in tests
      }
      const sessionId = crypto.randomUUID().replace(/-/g, "");
      const thread = ensureMockThread(sessionId, title);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ session_id: sessionId, ...thread }),
      });
      return;
    }

    await route.continue();
  });

  await page.route("**/api/chat", async (route: Route) => {
    const request = route.request();
    if (request.method() !== "POST") {
      await route.continue();
      return;
    }

    let message = "hello";
    let sessionId = crypto.randomUUID().replace(/-/g, "");
    try {
      const body = request.postDataJSON() as { message?: string; session_id?: string };
      message = body.message || message;
      sessionId = body.session_id || sessionId;
    } catch {
      // ignore malformed bodies in tests
    }

    const thread = ensureMockThread(sessionId);
    const now = nowSeconds();
    const userMessage: MockMessage = {
      id: `user-${now}`,
      role: "user",
      blocks: [{ type: "text", content: message }],
      created_at: now,
      lens_id: "general",
    };
    const assistantMessage: MockMessage = {
      id: `assistant-${now}`,
      role: "assistant",
      blocks: [{ type: "text", content: `Echo: ${message}` }],
      created_at: now + 1,
      lens_id: "general",
    };
    const history = mockMessages.get(sessionId) || [];
    history.push(userMessage, assistantMessage);
    mockMessages.set(sessionId, history);
    if (thread.thread_title === "New conversation") {
      thread.thread_title = message.slice(0, 60);
    }
    thread.preview = message;
    thread.message_count = history.length;
    thread.updated_at = now + 1;

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        session_id: sessionId,
        message: assistantMessage,
      }),
    });
  });

  await page.route("**/api/chat/messages/*/feedback", async (route: Route) => {
    const request = route.request();
    if (request.method() !== "POST") {
      await route.continue();
      return;
    }

    const parts = new URL(request.url()).pathname.split("/");
    const messageId = parts[parts.length - 2];
    let sessionId = "";
    let feedback: "helpful" | "not_helpful" = "helpful";
    try {
      const body = request.postDataJSON() as { session_id?: string; feedback?: "helpful" | "not_helpful" };
      sessionId = body.session_id || "";
      feedback = body.feedback || feedback;
    } catch {
      // ignore malformed bodies in tests
    }

    if (!mockFeedback.has(sessionId)) {
      mockFeedback.set(sessionId, new Map());
    }
    mockFeedback.get(sessionId)!.set(messageId, feedback);

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        saved: true,
        feedback: {
          id: `feedback-${messageId}`,
          message_id: messageId,
          session_id: sessionId,
          user_id: null,
          feedback,
          excerpt: "",
          created_at: nowSeconds(),
        },
      }),
    });
  });

  for (const service of ["llm", "plex", "radarr", "sonarr", "tmdb", "fanart", "tautulli"]) {
    await page.route(`**/api/setup/test/${service}`, async (route: Route) => {
      const payload =
        service === "plex"
          ? { ok: true, message: "Plex verified", sections: MOCK_SECTIONS }
          : { ok: true, message: `${service} verified` };

      certifiedServices.add(service);

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(payload),
      });
    });
  }

  await page.route("**/api/setup/wizard", async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }

    const response = await route.fetch();
    const body = await response.json();
    body.certifications = body.certifications || {};
    for (const service of certifiedServices) {
      body.certifications[service] = certificationEntry(true);
    }
    if (certifiedServices.has("llm")) {
      body.steps.infrastructure.llm_verified = true;
    }
    if (certifiedServices.has("plex")) {
      body.steps.infrastructure.plex_verified = true;
      body.steps.dropdown_mapping.plex_verified = true;
    }
    if (certifiedServices.has("radarr")) {
      body.steps.infrastructure.radarr_verified = true;
    }
    if (certifiedServices.has("sonarr")) {
      body.steps.infrastructure.sonarr_verified = true;
    }

    if (forceWizardIncomplete) {
      body.onboarding_complete = false;
      if (body.current_step === -1) {
        if (!body.steps?.identity_seed?.complete) body.current_step = 0;
        else if (!body.steps?.infrastructure?.complete) body.current_step = 1;
        else body.current_step = 2;
      }
    }

    await route.fulfill({
      status: response.status(),
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });

  await page.route("**/api/plex/sections", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_SECTIONS),
    });
  });

  await page.route("**/api/library/query**", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        total_matched: 142,
        returned: 25,
        offset: 0,
        has_more: true,
        items: [
          {
            title: "Alien",
            year: 1979,
            media_type: "movie",
            genres: ["Horror", "Sci-Fi"],
            view_count: 2,
            tmdb_id: 348,
          },
        ],
      }),
    });
  });

  await page.route("**/api/library/aggregate**", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        group_by: "decade",
        total_matched: 142,
        buckets: [{ decade: "1970s", decade_start: 1970, decade_end: 1979, count: 142 }],
      }),
    });
  });

  await page.route("**/api/library/overview", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        total: 5276,
        movies: 4474,
        shows: 802,
        decades: [{ decade: "1970s", decade_start: 1970, count: 142 }],
        top_genres: [{ genre: "Drama", count: 1868 }],
      }),
    });
  });

  await page.route("**/api/features", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        features: { multi_user_enabled: false, seerr_enabled: false, plex_collections_enabled: false },
        auth: {
          mode: "disabled",
          plex_login_enabled: true,
          oidc_enabled: false,
          local_login_enabled: false,
        },
        seerr: { link_on_login: true, require_linked_user_for_requests: false },
      }),
    });
  });

  await page.route("**/api/watchlist**", async (route: Route) => {
    const request = route.request();
    const method = request.method();
    if (method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [], count: 0 }),
      });
      return;
    }
    if (method === "POST") {
      const body = request.postDataJSON() as { title?: string; media_type?: string; tmdb_id?: number };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "mock-pin-1",
          user_id: null,
          title: body.title || "Mock title",
          media_type: body.media_type || "movie",
          tmdb_id: body.tmdb_id ?? null,
          tvdb_id: null,
          created_at: nowSeconds(),
        }),
      });
      return;
    }
    if (method === "DELETE") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ removed: true }),
      });
      return;
    }
    await route.continue();
  });

  await page.route("**/api/engagement/streak", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ session_count_30d: 1, streak_visible: false }),
    });
  });

  await page.route("**/api/persona/typing-phrases", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ phrases: ["Curator is thinking…", "Curator is weighing the options…"] }),
    });
  });

  await page.route("**/api/library/tv/progress**", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        group_by: "show",
        returned: 1,
        buckets: [
          {
            show_title: "The Wire",
            total_episodes: 60,
            watched_episodes: 30,
            unwatched_episodes: 30,
            completion_percent: 50.0,
          },
        ],
      }),
    });
  });

  await page.route("**/api/settings", async (route: Route) => {
    if (route.request().method() !== "PUT") {
      await route.continue();
      return;
    }

    let body: Record<string, unknown> = {};
    try {
      body = (route.request().postDataJSON() as Record<string, unknown>) ?? {};
    } catch {
      body = {};
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...body,
        llm_api_key: "",
        llm_api_key_set: Boolean(body.llm_api_key),
        plex_token: "",
        plex_token_set: Boolean(body.plex_token),
        radarr_api_key: "",
        radarr_api_key_set: Boolean(body.radarr_api_key),
        sonarr_api_key: "",
        sonarr_api_key_set: Boolean(body.sonarr_api_key),
      }),
    });
  });
}

export async function mockChatFailure(page: Page, detail = "LLM provider unavailable") {
  await page.route("**/api/chat", async (route: Route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail }),
    });
  });
}

export async function mockServiceFailure(page: Page, service: string, message = "Connection failed") {
  certifiedServices.delete(service);
  await page.route(`**/api/setup/test/${service}`, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: false, message }),
    });
  });
}

type FeatureFlags = {
  multi_user_enabled?: boolean;
  seerr_enabled?: boolean;
  plex_collections_enabled?: boolean;
};

export async function mockFeatures(page: Page, features: FeatureFlags = {}) {
  await page.route("**/api/features", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        features: {
          multi_user_enabled: false,
          seerr_enabled: false,
          plex_collections_enabled: false,
          ...features,
        },
        auth: {
          mode: features.multi_user_enabled ? "plex" : "disabled",
          plex_login_enabled: true,
          oidc_enabled: false,
          local_login_enabled: false,
        },
        seerr: { link_on_login: true, require_linked_user_for_requests: false },
      }),
    });
  });
}

export async function mockSetupStatus(
  page: Page,
  {
    radarrOk = false,
    sonarrOk = false,
    onboardingComplete = true,
  }: { radarrOk?: boolean; sonarrOk?: boolean; onboardingComplete?: boolean } = {},
) {
  await page.route("**/api/setup/status", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        onboarding_complete: onboardingComplete,
        ready_to_curate: true,
        checks: {
          plex: { ok: true, message: "Configured" },
          radarr: { ok: radarrOk, message: radarrOk ? "Configured" : "Optional for movie adds." },
          sonarr: { ok: sonarrOk, message: sonarrOk ? "Configured" : "Optional for TV adds." },
          tmdb: { ok: true, message: "Configured" },
          llm: { ok: true, message: "Configured" },
        },
      }),
    });
  });
}

export async function mockAuthUnauthenticated(page: Page) {
  await page.route("**/api/auth/me", async (route: Route) => {
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Not authenticated" }),
    });
  });
}

export async function mockAuthUser(page: Page, user = { id: "user-1", display_name: "Test User", role: "owner" }) {
  await page.route("**/api/auth/me", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ user }),
    });
  });
}

export async function mockPlexLogin(page: Page, user = { id: "user-1", display_name: "Test User", role: "owner" }) {
  let authenticated = false;
  let pinAuthorized = false;

  await page.route("**/api/auth/**", async (route: Route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    if (method === "POST" && path.endsWith("/api/auth/plex/pin")) {
      pinAuthorized = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: 42,
          code: "TEST",
          auth_url: "https://app.plex.tv/auth/#!?clientID=test&code=TEST",
          expires_in: 1800,
        }),
      });
      return;
    }

    if (method === "GET" && /\/api\/auth\/plex\/pin\/\d+$/.test(path)) {
      if (!pinAuthorized) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ authenticated: false, pending: true }),
        });
        return;
      }
      authenticated = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ user, authenticated: true, pending: false }),
      });
      return;
    }

    if (method === "POST" && path.endsWith("/api/auth/plex")) {
      authenticated = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ user, authenticated: true }),
      });
      return;
    }

    if (method === "GET" && path.endsWith("/api/auth/me")) {
      if (!authenticated) {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Not authenticated" }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ user }),
      });
      return;
    }

    await route.continue();
  });
}

/** Mock GET /api/jobs (and optional library stats) for Config sync progress UI. */
export async function mockLibrarySyncJobs(
  page: Page,
  jobs: Array<Record<string, unknown>> = [],
  stats: { movies?: number; shows?: number; last_sync?: unknown } | null = {
    movies: 12,
    shows: 3,
    last_sync: null,
  },
) {
  await page.route("**/api/jobs**", async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(jobs),
    });
  });

  if (stats !== null) {
    await page.route("**/api/library/stats", async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(stats),
      });
    });
  }
}

export function runningLibrarySyncJob(overrides: Record<string, unknown> = {}) {
  return {
    id: "sync-job-1",
    job_type: "library_sync",
    status: "running",
    created_at: Date.now() / 1000,
    started_at: Date.now() / 1000,
    finished_at: null,
    summary: {},
    progress: {
      phase: "movies",
      label: "Scanning movies",
      current: 120,
      total: 500,
      percent: 18,
      message: "Scanning Plex movies…",
    },
    error: null,
    ...overrides,
  };
}

export async function mockReviewConflictChat(page: Page) {
  await page.route("**/api/chat", async (route: Route) => {
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
      id: "assistant-conflict",
      role: "assistant",
      blocks: [
        { type: "text", content: "Saved your review locally. Plex has a different rating — choose below." },
        {
          type: "plex_rating_conflict",
          payload: {
            review: {
              title: "Inception",
              media_type: "movie",
              stars: 5,
              rating_key: "rk-1",
              tmdb_id: 27205,
            },
            plex_stars: 3,
            submitted_stars: 5,
          },
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
}

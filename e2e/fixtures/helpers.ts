import type { APIRequestContext } from "@playwright/test";

function e2eBaseURL() {
  // Keep in sync with playwright.config.ts — default 8799, never 8788 (SSH tunnel trap).
  return process.env.E2E_BASE_URL || `http://127.0.0.1:${process.env.E2E_PORT || "8799"}`;
}

export async function resetOnboarding(request: APIRequestContext, complete = false) {
  // Note: once onboarding_complete is true, the API preserves it (merge_secret_fields).
  // Wizard tests should open the UI via "Re-run onboarding wizard" when needed.
  // Setup-banner tests should mock /api/setup/status instead of relying on this flag alone.
  await request.put(`${e2eBaseURL()}/api/settings`, {
    data: {
      onboarding_complete: complete,
      plex_url: "",
      plex_token: "",
      plex_movie_section: complete ? "1" : "",
      plex_tv_section: complete ? "2" : "",
      radarr_url: "",
      radarr_api_key: "",
      sonarr_url: "",
      sonarr_api_key: "",
      llm_api_key: "",
      llm_base_url: "https://api.openai.com/v1",
      llm_provider: "openai",
      llm_model: "gpt-4o-mini",
      tmdb_api_key: "",
    },
  });
}

export async function completeOnboardingViaApi(request: APIRequestContext) {
  await request.put(`${e2eBaseURL()}/api/persona`, {
    data: { curator_name: "Test Curator" },
  });
  await request.put(`${e2eBaseURL()}/api/settings`, {
    data: {
      onboarding_complete: true,
      llm_provider: "openai",
      llm_model: "gpt-4o-mini",
      llm_base_url: "https://api.openai.com/v1",
      plex_url: "http://plex.local",
      plex_movie_section: "1",
      plex_tv_section: "2",
      radarr_url: "http://radarr.local",
      sonarr_url: "http://sonarr.local",
    },
  });
}

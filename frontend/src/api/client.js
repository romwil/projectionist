import { createId } from "../lib/id.js";

const API = "/api";
const SESSION_KEY = "curatorx_session";
const ACTIVE_LENS_KEY = "curatorx_active_lens";
const CHAT_TIMEOUT_MS = 120_000;

function parseApiErrorBody(text, statusText) {
  if (!text) return statusText || "Request failed";
  try {
    const data = JSON.parse(text);
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail
        .map((entry) => entry?.msg || entry?.message || String(entry))
        .join("; ");
    }
    if (data.error) return String(data.error);
    if (data.message) return String(data.message);
  } catch {
    // Plain-text or HTML error body
  }
  const trimmed = text.trim();
  return trimmed || statusText || "Request failed";
}

export function formatApiError(error) {
  if (!error) return "Request failed";
  if (error.name === "AbortError") {
    return "Request timed out. Check your LLM provider or try again.";
  }
  return error.message || "Request failed";
}

export async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    const error = new Error(parseApiErrorBody(text, response.statusText));
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return null;
  return response.json();
}

export function sessionId() {
  let value = localStorage.getItem(SESSION_KEY);
  if (!value) {
    value = createId({ compact: true });
    localStorage.setItem(SESSION_KEY, value);
  }
  return value;
}

export function setActiveSession(sessionId) {
  if (sessionId) {
    localStorage.setItem(SESSION_KEY, sessionId);
  } else {
    localStorage.removeItem(SESSION_KEY);
  }
}

export async function listThreads() {
  return api("/chat/threads");
}

export async function createThread(payload = {}) {
  return api("/chat/threads", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getThreadMessages(sessionId) {
  return api(`/chat/threads/${encodeURIComponent(sessionId)}/messages`);
}

export async function getFeatures() {
  return api("/features");
}

export async function getHealth() {
  return api("/health");
}

export async function getAuthMe() {
  const response = await fetch(`${API}/auth/me`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
  });
  if (response.status === 401) {
    return null;
  }
  if (!response.ok) {
    const text = await response.text();
    throw new Error(parseApiErrorBody(text, response.statusText));
  }
  return response.json();
}

export async function patchAuthMe(payload) {
  return api("/auth/me", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function startPlexPinLogin() {
  return api("/auth/plex/pin", { method: "POST" });
}

export async function pollPlexPinLogin(pinId) {
  return api(`/auth/plex/pin/${encodeURIComponent(pinId)}`);
}

export async function loginWithPlex(authToken) {
  return api("/auth/plex", {
    method: "POST",
    body: JSON.stringify({ auth_token: authToken }),
  });
}

export async function registerLocalUser(username, password) {
  return api("/auth/local/register", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export async function loginWithLocal(username, password) {
  return api("/auth/local/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export async function startOidcLogin() {
  return api("/auth/oidc/authorize");
}

export async function logout() {
  return api("/auth/logout", { method: "POST" });
}

export async function listUsers() {
  return api("/users");
}

export async function updateUserRole(userId, role) {
  return api(`/users/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    body: JSON.stringify({ role }),
  });
}

export async function patchUserDisabled(userId, disabled) {
  return api(`/users/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    body: JSON.stringify({ disabled: Boolean(disabled) }),
  });
}

export async function deleteUser(userId) {
  return api(`/users/${encodeURIComponent(userId)}`, {
    method: "DELETE",
  });
}

export async function syncUserSeerr(userId, authToken) {
  return api(`/users/${encodeURIComponent(userId)}/sync-seerr`, {
    method: "POST",
    body: JSON.stringify({ auth_token: authToken }),
  });
}

export async function listSeerrRequests(params = {}) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return api(`/requests${query ? `?${query}` : ""}`);
}

export async function getThreadFeedback(sessionId) {
  return api(`/chat/threads/${encodeURIComponent(sessionId)}/feedback`);
}

export async function submitMessageFeedback(messageId, sessionId, feedback) {
  if (!feedback) {
    const query = new URLSearchParams({ session_id: sessionId });
    return api(
      `/chat/messages/${encodeURIComponent(messageId)}/feedback?${query.toString()}`,
      { method: "DELETE" },
    );
  }
  return api(`/chat/messages/${encodeURIComponent(messageId)}/feedback`, {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, feedback }),
  });
}

export async function listReviews(params = {}) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return api(`/reviews${query ? `?${query}` : ""}`);
}

export async function saveReview(payload) {
  const response = await fetch(`${API}/reviews`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (response.status === 409 && data?.detail?.code === "plex_rating_conflict") {
    const conflict = new Error(data.detail.message || "Plex rating conflict");
    conflict.code = "plex_rating_conflict";
    conflict.conflict = data.detail;
    throw conflict;
  }
  if (!response.ok) {
    throw new Error(parseApiErrorBody(text, response.statusText));
  }
  return data;
}

export async function listReviewPrompts(limit = 5) {
  return api(`/reviews/prompts?limit=${encodeURIComponent(limit)}`);
}

export async function dismissReviewPrompt(promptId) {
  return api(`/reviews/prompts/${encodeURIComponent(promptId)}/dismiss`, {
    method: "POST",
  });
}

export async function updateThreadTitle(sessionId, threadTitle) {
  return api(`/chat/threads/${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    body: JSON.stringify({ thread_title: threadTitle }),
  });
}

export async function deleteThread(sessionId) {
  return api(`/chat/threads/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
}

export function getStoredActiveLensId() {
  return localStorage.getItem(ACTIVE_LENS_KEY);
}

export function setStoredActiveLensId(lensId) {
  if (lensId) {
    localStorage.setItem(ACTIVE_LENS_KEY, lensId);
  } else {
    localStorage.removeItem(ACTIVE_LENS_KEY);
  }
}

export async function listLenses() {
  return api("/lenses");
}

export async function getActiveLens() {
  return api("/lenses/active");
}

export async function setActiveLens(lensId) {
  const lens = await api("/lenses/active", {
    method: "PUT",
    body: JSON.stringify({ lens_id: lensId }),
  });
  setStoredActiveLensId(lens.lens_id);
  return lens;
}

export async function createLens(payload) {
  return api("/lenses", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateLens(lensId, payload) {
  return api(`/lenses/${encodeURIComponent(lensId)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function getPersona() {
  return api("/persona");
}

export async function getPersonaPresets() {
  return api("/persona/presets");
}

export async function getPersonaPreview(params = {}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) {
      query.set(key, String(value));
    }
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return api(`/persona/preview${suffix}`);
}

export async function putPersona(payload) {
  return api("/persona", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function getSystemConfig() {
  return api("/system-config");
}

export async function putSystemConfig(values) {
  return api("/system-config", {
    method: "PUT",
    body: JSON.stringify({ values }),
  });
}

export async function listWatchlist() {
  return api("/watchlist");
}

export async function addWatchlistPin(payload) {
  return api("/watchlist", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function removeWatchlistPin(pinId) {
  return api(`/watchlist/${encodeURIComponent(pinId)}`, {
    method: "DELETE",
  });
}

export async function getWatchlistSync() {
  return api("/watchlist/sync");
}

export async function updateWatchlistSync(payload) {
  return api("/watchlist/sync", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function runWatchlistSync(payload = { direction: "both" }) {
  return api("/watchlist/sync", {
    method: "POST",
    body: JSON.stringify(payload || { direction: "both" }),
  });
}

export async function listCuratedLists() {
  return api("/lists");
}

export async function createCuratedList(payload) {
  return api("/lists", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getCuratedList(listId) {
  return api(`/lists/${encodeURIComponent(listId)}`);
}

export async function updateCuratedList(listId, payload) {
  return api(`/lists/${encodeURIComponent(listId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteCuratedList(listId) {
  return api(`/lists/${encodeURIComponent(listId)}`, {
    method: "DELETE",
  });
}

export async function addCuratedListItem(listId, payload) {
  return api(`/lists/${encodeURIComponent(listId)}/items`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteCuratedListItem(listId, itemId) {
  return api(`/lists/${encodeURIComponent(listId)}/items/${encodeURIComponent(itemId)}`, {
    method: "DELETE",
  });
}

export async function getEngagementStreak() {
  return api("/engagement/streak");
}

export async function getPersonas() {
  return api("/personas");
}

export async function createPersona(data) {
  return api("/personas", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updatePersona(id, data) {
  return api(`/personas/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deletePersona(id) {
  return api(`/personas/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export async function setDefaultPersona(id) {
  return api(`/personas/${encodeURIComponent(id)}/default`, {
    method: "PUT",
  });
}

export async function getTypingPhrases() {
  return api("/persona/typing-phrases");
}

export async function listJobs() {
  return api("/jobs");
}

export async function sendChat(message, lensId, { timeoutMs = CHAT_TIMEOUT_MS, sessionId: explicitSessionId, personaId } = {}) {
  const body = { message, session_id: explicitSessionId || sessionId() };
  if (lensId) body.lens_id = lensId;
  if (personaId) body.persona_id = personaId;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await api("/chat", {
      method: "POST",
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * Stream chat via the SSE endpoint. Calls event handlers as tokens arrive.
 *
 * @param {string} message
 * @param {object} options
 * @param {string}   [options.sessionId]
 * @param {string}   [options.personaId]
 * @param {function} [options.onToken]    - ({content}) per text token
 * @param {function} [options.onToolCall] - ({name, status}) on tool start/complete
 * @param {function} [options.onDone]     - (fullPayload) when finished
 * @param {function} [options.onError]    - ({error}) on stream error
 * @param {AbortSignal} [options.signal]  - abort controller signal
 */
export async function sendChatStream(message, { sessionId: sid, personaId, onToken, onToolCall, onDone, onError, signal } = {}) {
  const params = new URLSearchParams({ message, session_id: sid || sessionId() });
  if (personaId) params.set("persona_id", personaId);

  const response = await fetch(`${API}/chat/stream?${params}`, {
    credentials: "include",
    signal,
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(parseApiErrorBody(text, response.statusText));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "message";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    for (;;) {
      const nlIndex = buffer.indexOf("\n");
      if (nlIndex === -1) break;
      const line = buffer.slice(0, nlIndex).trimEnd();
      buffer = buffer.slice(nlIndex + 1);

      if (line.startsWith("event:")) {
        currentEvent = line.slice(6).trim();
        continue;
      }
      if (!line.startsWith("data:")) {
        currentEvent = "message";
        continue;
      }
      const raw = line.slice(5).trim();
      if (!raw) continue;

      let parsed;
      try {
        parsed = JSON.parse(raw);
      } catch {
        continue;
      }

      switch (currentEvent) {
        case "token":
          onToken?.(parsed);
          break;
        case "tool_call":
          onToolCall?.(parsed);
          break;
        case "done":
          onDone?.(parsed);
          break;
        case "error":
          onError?.(parsed);
          break;
        default:
          break;
      }
      currentEvent = "message";
    }
  }
}

export function relativeTime(timestamp) {
  const seconds = Math.floor(Date.now() / 1000 - timestamp);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export { agentPulseTitle, resolveAgentPulse } from "../lib/agentPulse.js";

export const LLM_PROVIDER_DEFAULTS = {
  openai: "https://api.openai.com/v1",
  anthropic: "https://api.anthropic.com",
  gemini: "https://generativelanguage.googleapis.com/v1beta/openai",
  groq: "https://api.groq.com/openai/v1",
  mistral: "https://api.mistral.ai/v1",
  together: "https://api.together.xyz/v1",
  deepseek: "https://api.deepseek.com/v1",
  ollama: "http://localhost:11434/v1",
  openrouter: "https://openrouter.ai/api/v1",
  custom_openai_compatible: "",
  openai_compatible: "https://api.openai.com/v1",
};

export const LLM_MODEL_DEFAULTS = {
  openai: "gpt-4o-mini",
  anthropic: "claude-sonnet-4-6",
  gemini: "gemini-2.0-flash",
  groq: "llama-3.3-70b-versatile",
  mistral: "mistral-small-latest",
  together: "meta-llama/Llama-3.3-70B-Instruct-Turbo",
  deepseek: "deepseek-chat",
  ollama: "llama3",
  openrouter: "openai/gpt-4o-mini",
  custom_openai_compatible: "gpt-4o-mini",
  openai_compatible: "gpt-4o-mini",
};

export const ANTHROPIC_MODEL_OPTIONS = [
  "claude-sonnet-4-6",
  "claude-sonnet-4-20250514",
  "claude-sonnet-4-5-20250929",
  "claude-3-5-haiku-20241022",
  "claude-3-haiku-20240307",
  "claude-haiku-4-5",
];

const ANTHROPIC_MODEL_ALIASES = {
  "claude-sonnet-4": "claude-sonnet-4-6",
  "claude-sonnet-4-5": "claude-sonnet-4-5-20250929",
  "claude-sonnet-4-0": "claude-sonnet-4-6",
  "claude-3-5-sonnet": "claude-sonnet-4-6",
  "claude-3-5-sonnet-latest": "claude-sonnet-4-6",
  "claude-3-sonnet": "claude-sonnet-4-6",
  "claude-3-5-haiku": "claude-3-5-haiku-20241022",
  "claude-3-5-haiku-latest": "claude-3-5-haiku-20241022",
  "claude-3-haiku": "claude-3-haiku-20240307",
  "claude-3-haiku-latest": "claude-3-haiku-20240307",
  "claude-haiku-4-5-20251001": "claude-haiku-4-5",
};

const DEPRECATED_ANTHROPIC_MODELS = {
  "claude-3-5-sonnet-20241022": "claude-sonnet-4-6",
  "claude-3-5-sonnet-20240620": "claude-sonnet-4-6",
  "claude-3-opus-20240229": "claude-sonnet-4-6",
};

const ANTHROPIC_DATED_MODEL = /^claude-[a-z0-9.-]+-\d{8}$/i;

const OPENAI_MODEL_PREFIXES = ["gpt-", "o1", "o3", "o4", "text-embedding", "chatgpt-"];

export function modelLooksOpenai(model) {
  const cleaned = String(model || "").toLowerCase().trim();
  return OPENAI_MODEL_PREFIXES.some((prefix) => cleaned.startsWith(prefix));
}

export function modelLooksAnthropic(model) {
  return String(model || "").toLowerCase().trim().startsWith("claude");
}

export function normalizeAnthropicModel(model) {
  const defaultModel = LLM_MODEL_DEFAULTS.anthropic;
  const cleaned = String(model || "").trim();
  if (!cleaned) return defaultModel;
  if (modelLooksOpenai(cleaned)) return defaultModel;

  const lowered = cleaned.toLowerCase();
  if (ANTHROPIC_MODEL_ALIASES[lowered]) return ANTHROPIC_MODEL_ALIASES[lowered];
  if (DEPRECATED_ANTHROPIC_MODELS[lowered]) return DEPRECATED_ANTHROPIC_MODELS[lowered];
  if (lowered.endsWith("-latest")) return defaultModel;
  const known = ANTHROPIC_MODEL_OPTIONS.find((option) => option.toLowerCase() === lowered);
  if (known) return known;
  if (ANTHROPIC_DATED_MODEL.test(lowered)) return lowered;
  if (modelLooksAnthropic(lowered)) return defaultModel;
  return defaultModel;
}

export function resolveModelForProvider(provider, model) {
  const defaultModel = LLM_MODEL_DEFAULTS[provider] ?? LLM_MODEL_DEFAULTS.openai;
  const cleaned = String(model || "").trim();
  if (!cleaned) return defaultModel;
  if (provider === "anthropic") return normalizeAnthropicModel(cleaned);
  if (
    ["openai", "openai_compatible", "custom_openai_compatible"].includes(provider) &&
    modelLooksAnthropic(cleaned)
  ) {
    return LLM_MODEL_DEFAULTS.openai;
  }
  return cleaned;
}

export const LLM_PROVIDER_OPTIONS = [
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic (Claude)" },
  { value: "gemini", label: "Google Gemini" },
  { value: "groq", label: "Groq" },
  { value: "mistral", label: "Mistral" },
  { value: "together", label: "Together AI" },
  { value: "deepseek", label: "DeepSeek" },
  { value: "openrouter", label: "OpenRouter" },
  { value: "ollama", label: "Ollama (local)" },
  { value: "custom_openai_compatible", label: "Custom OpenAI-compatible" },
];

export const WIZARD_STEPS = [
  "identity_seed",
  "infrastructure",
  "dropdown_mapping",
];

export const AUTO_CERTIFY_SERVICES = [
  "llm",
  "plex",
  "radarr",
  "sonarr",
  "tmdb",
  "fanart",
  "tautulli",
  "seerr",
];

export async function getWizardStatus() {
  return api("/setup/wizard");
}

export async function getActiveContext() {
  return api("/context/active");
}

export async function getLibraryStats() {
  return api("/library/stats");
}

export async function getLibraryOverview() {
  return api("/library/overview");
}

export async function getLibraryAggregate(groupBy) {
  return api(`/library/aggregate?group_by=${encodeURIComponent(groupBy)}`);
}

export async function getLibraryHealth() {
  return api("/library/health");
}

export async function getPurgeCandidates() {
  return api("/library/purge-candidates");
}

export async function deletePurgeCandidates(ratingKeys) {
  return api("/library/purge-candidates/delete", {
    method: "POST",
    body: JSON.stringify({ rating_keys: ratingKeys }),
  });
}

export async function dismissPurgeCandidates(ratingKeys) {
  return api("/library/purge-candidates/dismiss", {
    method: "POST",
    body: JSON.stringify({ rating_keys: ratingKeys }),
  });
}

export async function getTvProgress() {
  return api("/library/tv/progress");
}

export async function startLibrarySync() {
  return api("/library/sync", { method: "POST" });
}

export async function getPlexSections() {
  return api("/plex/sections");
}

export async function getCertifications() {
  return api("/setup/certifications");
}

export async function getSettings() {
  return api("/settings");
}

export async function saveSettings(payload) {
  return api("/settings", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function rotateMcpKey(which) {
  return api("/settings/mcp-keys/rotate", {
    method: "POST",
    body: JSON.stringify({ which }),
  });
}

export async function clearMcpKey(which) {
  return api("/settings/mcp-keys/clear", {
    method: "POST",
    body: JSON.stringify({ which }),
  });
}

export async function testService(service, settings) {
  const payload = {
    ...settings,
    seerr_url: settings?.seerr?.url ?? settings?.seerr_url ?? "",
    seerr_api_key: settings?.seerr?.api_key ?? settings?.seerr_api_key ?? "",
  };
  return api(`/setup/test/${service}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listRequests(params = {}) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return api(`/requests${query ? `?${query}` : ""}`);
}

export async function proposeAction(body) {
  return api("/actions/propose", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function confirmAction(token, confirmed = true) {
  return api("/actions/confirm", {
    method: "POST",
    body: JSON.stringify({ token, confirmed }),
  });
}

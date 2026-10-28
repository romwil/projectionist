import { createId } from "../lib/id.js";
import { formatApiError, parseApiErrorBody } from "../lib/apiError.js";
import type {ApiError, AuthMe, ChatMessage, ExploreHubPayload, Features, Job, JsonObject, JsParam, QueryParams} from "./types";

export type {
  ApiError,
  AuthMe,
  AuthUser,
  ChatBlock,
  ChatMessage,
  ChatThread,
  ExploreHubPayload,
  FeatureFlags,
  Features,
  HubRail,
  HubWarming,
  Job,
  JobProgress,
  JsonObject,
  JsParam,
  LibraryItem,
  QueryParams,
  RecommendationExplanation,
  RecommendationReason,
  RecommendationWhy,
} from "./types";

export { formatApiError, parseApiErrorBody };

const API = "/api";
const SESSION_KEY = "curatorx_session";
const ACTIVE_LENS_KEY = "curatorx_active_lens";
const CHAT_TIMEOUT_MS = 120_000;

function throwApiError(text: string, statusText: string, status: number): never {
  const error = new Error(parseApiErrorBody(text, statusText, status)) as ApiError;
  error.status = status;
  throw error;
}

export async function api<T = JsonObject>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throwApiError(text, response.statusText, response.status);
  }
  if (response.status === 204) return null as T;
  const data: unknown = await response.json();
  return data as T;
}

export function sessionId() {
  let value = localStorage.getItem(SESSION_KEY);
  if (!value) {
    value = createId({ compact: true });
    localStorage.setItem(SESSION_KEY, value);
  }
  return value;
}

export function setActiveSession(nextSessionId: string | null | undefined) {
  if (nextSessionId) {
    localStorage.setItem(SESSION_KEY, nextSessionId);
  } else {
    localStorage.removeItem(SESSION_KEY);
  }
}

export async function listThreads() {
  return api("/chat/threads");
}

export async function createThread(payload: JsonObject = {}) {
  return api("/chat/threads", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getThreadMessages(sessionId: string) {
  return api<ChatMessage[]>(`/chat/threads/${encodeURIComponent(sessionId)}/messages`);
}

export async function saveLibraryPage(payload: JsonObject) {
  return api("/saved-library", { method: "POST", body: JSON.stringify(payload) });
}

export async function listLibraryPages(query: string = "") {
  return api(`/saved-library?q=${encodeURIComponent(query)}`);
}

export async function getLibraryPage(pageId: string) {
  return api(`/saved-library/${encodeURIComponent(pageId)}`);
}

export async function deleteLibraryPage(pageId: string) {
  return api(`/saved-library/${encodeURIComponent(pageId)}`, { method: "DELETE" });
}

/** Notify household peers about an account-scoped saved page (never a public link). */
export async function shareLibraryPage(pageId: string, payload: JsonObject) {
  return api(`/saved-library/${encodeURIComponent(pageId)}/share`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getFeatures() {
  return api<Features>("/features");
}

export async function getSetupHandshake() {
  return api("/setup/handshake");
}

export async function commitSetup(payload: JsonObject) {
  return api("/setup/commit", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function testPlex(settings: JsonObject = {}) {
  return testService("plex", settings);
}

export async function testTmdb(settings: JsonObject = {}) {
  return testService("tmdb", settings);
}

export async function getPlexMachineId() {
  const payload = await api("/plex/machine-id");
  return String(payload?.machine_id || "").trim();
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
    throw new Error(parseApiErrorBody(text, response.statusText, response.status));
  }
  const data: JsonObject = await response.json();
  return data as AuthMe;
}

export async function patchAuthMe(payload: JsonObject) {
  return api("/auth/me", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

/** Upload a profile picture (multipart). Returns `{ user, authenticated }`. */
export async function uploadAuthAvatar(file: File) {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(`${API}/auth/me/avatar`, {
    method: "POST",
    credentials: "include",
    body,
  });
  if (!response.ok) {
    const text = await response.text();
    throwApiError(text, response.statusText, response.status);
  }
  const data: JsonObject = await response.json();
  return data as AuthMe;
}

export { resolveAvatarSrc } from "../lib/avatarSrc.js";

export async function listHouseholdPeers() {
  return api("/household/peers");
}

export async function listRecommendations(params: QueryParams = {}) {
  const query = new URLSearchParams();
  if (params.unread_only) query.set("unread_only", "true");
  if (params.limit) query.set("limit", String(params.limit));
  const suffix = query.toString() ? `?${query}` : "";
  return api(`/recommendations${suffix}`);
}

export async function createRecommendations(payload: JsonObject) {
  return api("/recommendations", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function markRecommendationsSeen(payload: JsonObject) {
  return api("/recommendations/seen", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listNotifications(params: QueryParams = {}) {
  const query = new URLSearchParams();
  if (params.unread_only) query.set("unread_only", "true");
  if (params.status) query.set("status", String(params.status));
  if (params.sort) query.set("sort", String(params.sort));
  if (params.limit) query.set("limit", String(params.limit));
  if (params.offset) query.set("offset", String(params.offset));
  if (params.kind) query.set("kind", String(params.kind));
  const suffix = query.toString() ? `?${query}` : "";
  return api(`/notifications${suffix}`);
}

export async function markNotificationsRead(payload: JsonObject) {
  return api("/notifications/read", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function bindNotificationThread(notificationId: string, sessionId: string) {
  return api(`/notifications/${encodeURIComponent(notificationId)}/thread`, {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export async function markNotificationsSeen(payload: JsonObject) {
  return api("/notifications/seen", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listWhispers(params: QueryParams = {}) {
  const query = new URLSearchParams();
  if (params.unread_only) query.set("unread_only", "true");
  if (params.limit) query.set("limit", String(params.limit));
  const suffix = query.toString() ? `?${query}` : "";
  return api(`/whispers${suffix}`);
}

export async function markWhispersSeen(payload: JsonObject) {
  return api("/whispers/seen", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function testMailSend(payload: JsonObject = {}) {
  return api("/admin/mail/test", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function testAppriseSend(payload: JsonObject = {}) {
  return api("/admin/apprise/test", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Member self-serve: test a single Apprise destination URL. */
export async function testMyAppriseSend(payload: JsonObject = {}) {
  return api("/auth/me/apprise/test", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Owner-only: fan out the weekly newsletter now (self / selected / all opt-ins). */
export async function generateWeeklyNewsletter(payload: JsonObject = {}) {
  return api("/admin/weekly-newsletter/generate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getWeeklyNewsletterStatus() {
  return api("/admin/weekly-newsletter/status");
}

export async function cancelWeeklyNewsletter() {
  return api("/admin/weekly-newsletter/cancel", { method: "POST" });
}

/** Member: fetch own Year in Review reel for a calendar year. */
export async function getYearInReview(year: number) {
  return api(`/year-in-review/${encodeURIComponent(year)}`);
}

/** Owner-only: generate (and optionally notify) own Year in Review. */
export async function generateYearInReview(payload: JsonObject = {}) {
  return api("/admin/year-in-review/generate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getYearInReviewStatus() {
  return api("/admin/year-in-review/status");
}

export async function cancelYearInReview() {
  return api("/admin/year-in-review/cancel", { method: "POST" });
}

/** Owner: list Plex movies missing from Radarr. */
export async function listRadarrOwnedNotIndexed(limit: number = 50) {
  return api(`/admin/radarr/owned-not-indexed?limit=${encodeURIComponent(limit)}`);
}

/** Owner: register on-disk movies into Radarr without download search. */
export async function registerRadarrExisting(payload: JsonObject = {}) {
  return api("/admin/radarr/register-existing", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Owner: poll Register in Radarr progress. */
export async function getRadarrRegisterStatus() {
  return api("/admin/radarr/register-existing/status");
}

/** Owner: cancel remaining Register in Radarr titles. */
export async function cancelRadarrRegister() {
  return api("/admin/radarr/register-existing/cancel", { method: "POST" });
}

/** Owner: start a Sonarr aired-missing scan (background job). */
export async function startSonarrMissingScan(payload: JsonObject = {}) {
  return api("/admin/sonarr/missing/scan", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Owner: poll Sonarr missing-scan progress and last result. */
export async function getSonarrMissingStatus() {
  return api("/admin/sonarr/missing/status");
}

/** Owner: queue EpisodeSearch batches for scanned (or supplied) episode ids. */
export async function searchSonarrMissing(payload: JsonObject = {}) {
  return api("/admin/sonarr/missing/search", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Owner: cancel remaining queued EpisodeSearch commands in Sonarr. */
export async function cancelSonarrMissing() {
  return api("/admin/sonarr/missing/cancel", { method: "POST" });
}

export async function startPlexPinLogin({ inviteToken }: { inviteToken?: string } = {}) {
  const search = new URLSearchParams();
  if (inviteToken) search.set("invite_token", inviteToken);
  return api(`/auth/plex/pin${search.toString() ? `?${search}` : ""}`, { method: "POST" });
}

export async function pollPlexPinLogin(pinId: string, { peek }: { peek?: boolean } = {}) {
  const search = peek ? "?peek=1" : "";
  return api(`/auth/plex/pin/${encodeURIComponent(pinId)}${search}`);
}

export async function linkPlexAccount({ pinId, password }: { pinId?: string; password?: string }) {
  return api("/auth/plex/link", {
    method: "POST",
    body: JSON.stringify({ pin_id: pinId, password }),
  });
}

export async function loginWithPlex(authToken: string, { inviteToken }: { inviteToken?: string } = {}) {
  return api("/auth/plex", {
    method: "POST",
    body: JSON.stringify({
      auth_token: authToken,
      ...(inviteToken ? { invite_token: inviteToken } : {}),
    }),
  });
}

export async function registerLocalUser(username: string, password: string) {
  return api("/auth/local/register", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export async function loginWithLocal(username: string, password: string) {
  return api("/auth/local/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export async function startOidcLogin({ inviteToken }: { inviteToken?: string } = {}) {
  const search = new URLSearchParams();
  if (inviteToken) search.set("invite_token", inviteToken);
  return api(`/auth/oidc/authorize${search.toString() ? `?${search}` : ""}`);
}

export async function logout() {
  return api("/auth/logout", { method: "POST" });
}

export async function listUsers() {
  return api("/users");
}

export async function updateUserRole(userId: string, role: string) {
  return api(`/users/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    body: JSON.stringify({ role }),
  });
}

export async function patchUserDisabled(userId: string, disabled: boolean) {
  return api(`/users/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    body: JSON.stringify({ disabled: Boolean(disabled) }),
  });
}

export async function patchUserYouthMode(userId: string, isYouth: boolean) {
  return api(`/users/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    body: JSON.stringify({ is_youth: Boolean(isYouth) }),
  });
}

export async function deleteUser(userId: string) {
  return api(`/users/${encodeURIComponent(userId)}`, {
    method: "DELETE",
  });
}

export async function syncUserSeerr(userId: string, authToken: string) {
  return api(`/users/${encodeURIComponent(userId)}/sync-seerr`, {
    method: "POST",
    body: JSON.stringify({ auth_token: authToken }),
  });
}

export async function listSeerrRequests(params: QueryParams = {}) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return api(`/requests${query ? `?${query}` : ""}`);
}

export async function getThreadFeedback(sessionId: string) {
  return api(`/chat/threads/${encodeURIComponent(sessionId)}/feedback`);
}

export async function submitMessageFeedback(messageId: string, sessionId: string, feedback: string) {
  if (!feedback) {
    const query = new URLSearchParams({ session_id: sessionId });
    return api(`/chat/messages/${encodeURIComponent(messageId)}/feedback?${query.toString()}`, {
      method: "DELETE",
    });
  }
  return api(`/chat/messages/${encodeURIComponent(messageId)}/feedback`, {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, feedback }),
  });
}

export async function listReviews(params: QueryParams = {}) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return api(`/reviews${query ? `?${query}` : ""}`);
}

export async function saveReview(payload: JsonObject) {
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
    const conflict = new Error(data.detail.message || "Plex rating conflict") as ApiError;
    conflict.code = "plex_rating_conflict";
    conflict.conflict = data.detail;
    throw conflict;
  }
  if (!response.ok) {
    throw new Error(parseApiErrorBody(text, response.statusText, response.status));
  }
  return data;
}

export async function listReviewPrompts(limit: number = 5) {
  return api(`/reviews/prompts?limit=${encodeURIComponent(limit)}`);
}

export async function dismissReviewPrompt(promptId: string | number) {
  return api(`/reviews/prompts/${encodeURIComponent(promptId)}/dismiss`, {
    method: "POST",
  });
}

export async function updateThreadTitle(sessionId: string, threadTitle: JsonObject) {
  return api(`/chat/threads/${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    body: JSON.stringify({ thread_title: threadTitle }),
  });
}

export async function deleteThread(sessionId: string) {
  return api(`/chat/threads/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
}

export function getStoredActiveLensId() {
  return localStorage.getItem(ACTIVE_LENS_KEY);
}

export function setStoredActiveLensId(lensId: string) {
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

export async function setActiveLens(lensId: string) {
  const lens = await api("/lenses/active", {
    method: "PUT",
    body: JSON.stringify({ lens_id: lensId }),
  });
  setStoredActiveLensId(lens.lens_id);
  return lens;
}

export async function createLens(payload: JsonObject) {
  return api("/lenses", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateLens(lensId: string, payload: JsonObject) {
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

export async function getPersonaPreview(params: QueryParams = {}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) {
      query.set(key, String(value));
    }
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return api(`/persona/preview${suffix}`);
}

export async function putPersona(payload: JsonObject) {
  return api("/persona", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function getSystemConfig() {
  return api("/system-config");
}

export async function getAdminLogs({ limit = 300, level, logger, q }: JsonObject = {}) {
  const params = new URLSearchParams();
  if (limit != null) params.set("limit", String(limit));
  if (level) params.set("level", level);
  if (logger) params.set("logger", logger);
  if (q) params.set("q", q);
  const qs = params.toString();
  return api(`/admin/logs${qs ? `?${qs}` : ""}`);
}

export async function putSystemConfig(values: JsonObject) {
  return api("/system-config", {
    method: "PUT",
    body: JSON.stringify({ values }),
  });
}

export async function listWatchlist({ enrich = false }: JsonObject = {}) {
  return api(`/watchlist${enrich ? "?enrich=1" : ""}`);
}

export async function addWatchlistPin(payload: JsonObject) {
  return api("/watchlist", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function removeWatchlistPin(pinId: string) {
  return api(`/watchlist/${encodeURIComponent(pinId)}`, {
    method: "DELETE",
  });
}

export async function getWatchlistSync() {
  return api("/watchlist/sync");
}

export async function updateWatchlistSync(payload: JsonObject) {
  return api("/watchlist/sync", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function runWatchlistSync(payload: JsonObject = { direction: "both" }) {
  return api("/watchlist/sync", {
    method: "POST",
    body: JSON.stringify(payload || { direction: "both" }),
  });
}

export async function listCuratedLists() {
  return api("/lists");
}

export async function createCuratedList(payload: JsonObject) {
  return api("/lists", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getCuratedList(listId: string) {
  return api(`/lists/${encodeURIComponent(listId)}`);
}

export async function updateCuratedList(listId: string, payload: JsonObject) {
  return api(`/lists/${encodeURIComponent(listId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteCuratedList(listId: string) {
  return api(`/lists/${encodeURIComponent(listId)}`, {
    method: "DELETE",
  });
}

export async function addCuratedListItem(listId: string, payload: JsonObject) {
  return api(`/lists/${encodeURIComponent(listId)}/items`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteCuratedListItem(listId: string, itemId: string | number) {
  return api(`/lists/${encodeURIComponent(listId)}/items/${encodeURIComponent(itemId)}`, {
    method: "DELETE",
  });
}

/** Owner authoring: set a course step's note and/or ordering position. */
export async function updateCuratedListItem(listId: string, itemId: string | number, payload: JsonObject) {
  return api(`/lists/${encodeURIComponent(listId)}/items/${encodeURIComponent(itemId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

/** Owner-only: publish a list to household members or make it private again. */
export async function setCuratedListVisibility(listId: string, visibility: string) {
  return api(`/lists/${encodeURIComponent(listId)}`, {
    method: "PATCH",
    body: JSON.stringify({ visibility }),
  });
}

/** Household-visible published collections/courses (any signed-in member). */
export async function listPublishedCollections() {
  return api("/collections");
}

export async function getPublishedCollection(listId: string) {
  return api(`/collections/${encodeURIComponent(listId)}`);
}

export async function createAccessRequest(payload: JsonObject) {
  return api("/access-requests", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listAccessRequests({ status }: JsonObject = {}) {
  const search = new URLSearchParams();
  if (status) search.set("status", status);
  return api(`/admin/access-requests${search.toString() ? `?${search}` : ""}`);
}

export async function approveAccessRequest(requestId: string | number, payload: JsonObject = {}) {
  return api(`/admin/access-requests/${encodeURIComponent(requestId)}/approve`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function denyAccessRequest(requestId: string | number) {
  return api(`/admin/access-requests/${encodeURIComponent(requestId)}/deny`, {
    method: "POST",
  });
}

export async function listInvites({ status }: JsonObject = {}) {
  const search = new URLSearchParams();
  if (status) search.set("status", status);
  return api(`/admin/invites${search.toString() ? `?${search}` : ""}`);
}

export async function createInvite(payload: JsonObject = {}) {
  return api("/admin/invites", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function revokeInvite(inviteId: string | number) {
  return api(`/admin/invites/${encodeURIComponent(inviteId)}/revoke`, {
    method: "POST",
  });
}

export async function validateInvite(token: string) {
  const search = new URLSearchParams({ token });
  return api(`/invites/validate?${search}`);
}

export async function redeemInviteLocal({ token, username, password }: JsonObject) {
  return api("/invites/redeem/local", {
    method: "POST",
    body: JSON.stringify({ token, username, password }),
  });
}

export async function createMediaIssue(payload: JsonObject) {
  return api("/media-issues", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listMediaIssues(params: QueryParams = {}) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  return api(`/media-issues${search.toString() ? `?${search}` : ""}`);
}

export async function listStagedAugmentations({ status, task_name, limit }: JsonObject = {}) {
  const search = new URLSearchParams();
  if (status) search.set("status", status);
  if (task_name) search.set("task_name", task_name);
  if (limit != null) search.set("limit", String(limit));
  return api(`/admin/staged-augmentations${search.toString() ? `?${search}` : ""}`);
}

export async function approveStagedAugmentation(rowId: string | number, payload: JsonObject = {}) {
  return api(`/admin/staged-augmentations/${encodeURIComponent(rowId)}/approve`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function rejectStagedAugmentation(rowId: string | number) {
  return api(`/admin/staged-augmentations/${encodeURIComponent(rowId)}/reject`, {
    method: "POST",
  });
}

export async function dismissPlotNeighbor(itemId: string | number, neighborId: string | number) {
  return api(
    `/library/neighbors/${encodeURIComponent(itemId)}/${encodeURIComponent(neighborId)}/dismiss`,
    { method: "POST" },
  );
}

export async function getKnowledgeOpsSummary() {
  return api("/admin/knowledge-ops/summary");
}

export async function getKnowledgeOpsFunnel({ min_hit_count }: JsonObject = {}) {
  const search = new URLSearchParams();
  if (min_hit_count != null) search.set("min_hit_count", String(min_hit_count));
  return api(`/admin/knowledge-ops/funnel${search.toString() ? `?${search}` : ""}`);
}

export async function getKnowledgeOpsTaxonomyRegistry() {
  return api("/admin/knowledge-ops/taxonomy-registry");
}

export async function getKnowledgeOpsTelemetryTrend({ days }: JsonObject = {}) {
  const search = new URLSearchParams();
  if (days != null) search.set("days", String(days));
  return api(`/admin/knowledge-ops/telemetry/trend${search.toString() ? `?${search}` : ""}`);
}

export async function getKnowledgeOpsTelemetryTopEvents({ event_type, entity_type, limit }: JsonObject = {}) {
  const search = new URLSearchParams();
  if (event_type) search.set("event_type", event_type);
  if (entity_type) search.set("entity_type", entity_type);
  if (limit != null) search.set("limit", String(limit));
  return api(`/admin/knowledge-ops/telemetry/top-events${search.toString() ? `?${search}` : ""}`);
}

export async function getKnowledgeOpsStagedAggregates() {
  return api("/admin/knowledge-ops/staged-aggregates");
}

export async function updateMediaIssue(issueId: string, payload: JsonObject) {
  return api(`/media-issues/${encodeURIComponent(issueId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function repairMediaIssue(issueId: string) {
  return api(`/media-issues/${encodeURIComponent(issueId)}/repair`, { method: "POST" });
}

export async function getEngagementStreak() {
  return api("/engagement/streak");
}

export async function getEngagementSummary() {
  return api("/engagement/summary");
}

export async function getJourneyExploration() {
  return api("/journey/exploration");
}

export async function postCourseProgress(listId: string, { position = 0, completed = false }: JsonObject = {}) {
  return api(`/engagement/courses/${encodeURIComponent(listId)}/progress`, {
    method: "POST",
    body: JSON.stringify({ position, completed }),
  });
}

export async function startCourseSyllabus(listId: string) {
  return api(`/syllabus/courses/${encodeURIComponent(listId)}`, { method: "POST" });
}

export async function getCourseSyllabus(listId: string) {
  return api(`/syllabus/courses/${encodeURIComponent(listId)}`);
}

export async function updateSyllabusSession(sessionId: string, payload: JsonObject = {}) {
  return api(`/syllabus/sessions/${encodeURIComponent(sessionId)}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getTasteProfile() {
  return api("/taste");
}

export async function patchTasteProfile(clusters: JsonObject[]) {
  return api("/taste", {
    method: "PATCH",
    body: JSON.stringify({ clusters }),
  });
}

export async function deleteTasteCluster(clusterTag: string) {
  return api(`/taste/${encodeURIComponent(clusterTag)}`, { method: "DELETE" });
}

export async function submitTasteQuiz({ likes = [], dislikes = [] }: JsonObject = {}) {
  return api("/taste/quiz", {
    method: "POST",
    body: JSON.stringify({ likes, dislikes }),
  });
}

export async function getPickForMeFeed({ limit = 8 }: JsonObject = {}) {
  const search = new URLSearchParams({ limit: String(limit) });
  return api(`/library/feeds/pick-for-me?${search}`);
}

/** Matches Plex Continue Watching's on-deck window (projectionist.library.feeds.EXPLORE_RAIL_LIMIT). */
export const EXPLORE_RAIL_LIMIT = 50;

/** Single Explore home payload (rails + pulse). Prefer over per-rail fetches. */
export async function getExploreHub({ limit = EXPLORE_RAIL_LIMIT, refresh = false }: JsonObject = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (refresh) params.set("refresh", "true");
  return api<ExploreHubPayload>(`/library/feeds/hub?${params}`);
}

export async function syllabusPublishHandoff(listId: string, { confirm = false, target = "plex" }: JsonObject = {}) {
  return api(`/syllabus/courses/${encodeURIComponent(listId)}/publish-handoff`, {
    method: "POST",
    body: JSON.stringify({ confirm, target }),
  });
}

export async function anniversaryLiveStarter({ confirm = false, motifHint = "" }: JsonObject = {}) {
  return api("/admin/live-channels/anniversary-starter", {
    method: "POST",
    body: JSON.stringify({ confirm, motif_hint: motifHint }),
  });
}

export async function downloadAdminBackupSnapshot() {
  const response = await fetch("/api/admin/backup/snapshot", {
    credentials: "include",
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Backup failed (${response.status})`);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = /filename="([^"]+)"/.exec(disposition);
  return { blob, filename: match?.[1] || "projectionist-snapshot.zip" };
}

/** Owner-only: review a Youth-flagged account's memory notes (fail-closed on the server). */
export async function getUserMemory(userId: string) {
  return api(`/users/${encodeURIComponent(userId)}/memory`);
}

/** Owner-only: list recent reversible grooming actions for the undo UI. */
export async function listGroomingActions({ limit = 20 }: JsonObject = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  return api(`/admin/grooming/actions?${params}`);
}

/** Owner-only: undo (restore) a destructive grooming action by id. */
export async function undoGroomingAction(actionId: string) {
  return api(`/admin/grooming/actions/${encodeURIComponent(actionId)}/undo`, {
    method: "POST",
  });
}

/** Owner-only: latest weekly in-app digest snapshot plus recent history. */
export async function getWeeklyDigest({ limit = 8 }: JsonObject = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  return api(`/admin/weekly-digest?${params}`);
}

/** Household: read-only Live Channels guide snapshot (empty-safe when off). */
export async function getLiveChannelsOnNow() {
  return api("/live-channels/on-now");
}

/** Household: wider channel × time guide for `/live` EPG (1–12 hours). */
export async function getLiveChannelsGuide({ hours = 6, timeoutMs = 8000 }: JsonObject = {}) {
  const params = new URLSearchParams({ hours: String(hours) });
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await api(`/live-channels/guide?${params}`, { signal: controller.signal });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      const error = new Error("The guide is taking too long.");
      error.name = "TimeoutError";
      throw error;
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

/** Household: warm + start-over a station before Projectionist playback. */
export async function tuneLiveChannel(channelId: string) {
  return api("/live-channels/tune", {
    method: "POST",
    body: JSON.stringify({ channel_id: String(channelId || "") }),
  });
}

/** Household: start an in-app library HLS session (movie / episode / show key). */
export async function startLibraryPlayback(ratingKey: string, { startOver = false }: JsonObject = {}) {
  return api("/library/playback/start", {
    method: "POST",
    body: JSON.stringify({
      rating_key: String(ratingKey || ""),
      start_over: Boolean(startOver),
    }),
  });
}

export async function seekLibraryPlayback(sessionId: string, offsetMs: number) {
  return api(`/library/playback/${encodeURIComponent(sessionId)}/seek`, {
    method: "POST",
    body: JSON.stringify({ offset_ms: Math.max(0, Math.floor(Number(offsetMs) || 0)) }),
  });
}

/** Restart the Plex transcode with a burn-in stream, or Off (`subtitles=none`). */
export async function setLibraryPlaybackSubtitles(sessionId: string, { subtitleStreamId = null, offsetMs = 0 }: JsonObject = {}) {
  const raw = subtitleStreamId == null ? "" : String(subtitleStreamId).trim();
  return api(`/library/playback/${encodeURIComponent(sessionId)}/subtitles`, {
    method: "POST",
    body: JSON.stringify({
      subtitle_stream_id: raw || null,
      offset_ms: Math.max(0, Math.floor(Number(offsetMs) || 0)),
    }),
  });
}

export async function progressLibraryPlayback(sessionId: string, payload: JsonObject) {
  return api(`/library/playback/${encodeURIComponent(sessionId)}/progress`, {
    method: "POST",
    body: JSON.stringify({
      state: String(payload?.state || "playing"),
      time_ms: Math.max(0, Math.floor(Number(payload?.time_ms) || 0)),
      duration_ms: Math.max(0, Math.floor(Number(payload?.duration_ms) || 0)),
    }),
  });
}

export async function stopLibraryPlayback(sessionId: string, payload: JsonObject = {}) {
  return api(`/library/playback/${encodeURIComponent(sessionId)}/stop`, {
    method: "POST",
    body: JSON.stringify({
      time_ms:
        payload.time_ms == null ? undefined : Math.max(0, Math.floor(Number(payload.time_ms) || 0)),
      duration_ms:
        payload.duration_ms == null
          ? undefined
          : Math.max(0, Math.floor(Number(payload.duration_ms) || 0)),
    }),
  });
}

/** Independent preroll bumper for this browser (204 → null when none). */
export async function fetchNextPreroll(context: string = "movie") {
  const params = new URLSearchParams({ context: String(context || "movie") });
  return api(`/preroll/next?${params}`);
}

/** Weather Channel cable experience (Open-Meteo egress + optional local muzak). */
export async function getLiveWeatherChannel() {
  return api("/live/weather");
}

/** Open-Meteo place search (ZIP, city/state, or city/country). */
export async function searchWeatherPlaces(query: string) {
  const params = new URLSearchParams({ q: String(query || "").trim() });
  return api(`/weather/places?${params}`);
}

/** Owner folder browser rooted at container-visible media mounts. */
export async function browseLiveMedia(path: string = "") {
  const params = new URLSearchParams();
  const cleaned = String(path || "").trim();
  if (cleaned) params.set("path", cleaned);
  const suffix = params.toString() ? `?${params}` : "";
  return api(`/admin/live/media-browser${suffix}`);
}

/** Save the Weather Channel music folder (empty clears it). */
export async function saveLiveMuzakFolder(path: string) {
  return api("/admin/live/muzak-folder", {
    method: "PUT",
    body: JSON.stringify({ path: String(path || "") }),
  });
}

/** Owner-only: assemble and store the digest for the current week on demand. */
export async function generateWeeklyDigest() {
  return api("/admin/weekly-digest/generate", { method: "POST" });
}

export async function getWeeklyDigestStatus() {
  return api("/admin/weekly-digest/status");
}

export async function cancelWeeklyDigest() {
  return api("/admin/weekly-digest/cancel", { method: "POST" });
}

export async function getPersonas() {
  return api("/personas");
}

export async function createPersona(data: JsonObject) {
  return api("/personas", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updatePersona(id: string, data: JsonObject) {
  return api(`/personas/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deletePersona(id: string) {
  return api(`/personas/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export async function setDefaultPersona(id: string) {
  return api(`/personas/${encodeURIComponent(id)}/default`, {
    method: "PUT",
  });
}

export async function getTypingPhrases() {
  return api("/persona/typing-phrases");
}

export async function listJobs() {
  return api<Job[]>("/jobs");
}

export async function sendChat(message: JsonObject,
  lensId?: string,
  {
    timeoutMs = CHAT_TIMEOUT_MS,
    sessionId: explicitSessionId,
    personaId,
  }: { timeoutMs?: number; sessionId?: string; personaId?: string } = {},
) {
  const body: JsonObject = { message, session_id: explicitSessionId || sessionId() };
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
 * Stream chat via POST /api/chat/stream (SSE). Native EventSource cannot POST —
 * this uses fetch + a body reader and must not fall back to EventSource.
 *
 * @param {string} message
 * @param {object} options
 * @param {string}   [options.sessionId]
 * @param {string}   [options.personaId]
 * @param {function} [options.onToken]    - ({content}) per text token
 * @param {function} [options.onToolCall] - ({name, status, args?, summary?}) on tool start/complete
 * @param {function} [options.onDone]     - (fullPayload) when finished
 * @param {function} [options.onError]    - ({error}) on stream error
 * @param {AbortSignal} [options.signal]  - abort controller signal
 */
export async function sendChatStream(message: JsonObject,
  {
    sessionId: sid,
    personaId,
    onToken,
    onToolCall,
    onDone,
    onError,
    signal,
  }: {
    sessionId?: string;
    personaId?: string;
    onToken?: (payload: JsonObject) => void;
    onToolCall?: (payload: JsonObject) => void;
    onDone?: (payload: JsonObject) => void;
    onError?: (payload: JsonObject) => void;
    signal?: AbortSignal;
  } = {},
) {
  const body: JsonObject = { message, session_id: sid || sessionId() };
  if (personaId) body.persona_id = personaId;

  const response = await fetch(`${API}/chat/stream`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(parseApiErrorBody(text, response.statusText, response.status));
  }

  const reader = response.body?.getReader();
  if (!reader) {
    onError?.({ error: "The response could not be read." });
    return;
  }
  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "message";
  // A stream that closes without `done` or `error` (proxy cut, server crash
  // after a tool side effect) must not leave a blank assistant bubble.
  let sawTerminalEvent = false;

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
          sawTerminalEvent = true;
          onDone?.(parsed);
          break;
        case "error":
          sawTerminalEvent = true;
          onError?.(parsed);
          break;
        default:
          break;
      }
      currentEvent = "message";
    }
  }

  if (!sawTerminalEvent && !signal?.aborted) {
    onError?.({
      error:
        "The response stopped before it finished. If you asked me to create or change something, " +
        "check whether it went through before retrying.",
    });
  }
}

export function relativeTime(timestamp: number) {
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

export const LLM_MODEL_DEFAULTS: Record<string, string> = {
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

const ANTHROPIC_MODEL_ALIASES: Record<string, string> = {
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

const DEPRECATED_ANTHROPIC_MODELS: Record<string, string> = {
  "claude-3-5-sonnet-20241022": "claude-sonnet-4-6",
  "claude-3-5-sonnet-20240620": "claude-sonnet-4-6",
  "claude-3-opus-20240229": "claude-sonnet-4-6",
};

const ANTHROPIC_DATED_MODEL = /^claude-[a-z0-9.-]+-\d{8}$/i;

const OPENAI_MODEL_PREFIXES = ["gpt-", "o1", "o3", "o4", "text-embedding", "chatgpt-"];

export function modelLooksOpenai(model: string) {
  const cleaned = String(model || "")
    .toLowerCase()
    .trim();
  return OPENAI_MODEL_PREFIXES.some((prefix) => cleaned.startsWith(prefix));
}

export function modelLooksAnthropic(model: string) {
  return String(model || "")
    .toLowerCase()
    .trim()
    .startsWith("claude");
}

export function normalizeAnthropicModel(model: string) {
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

export function resolveModelForProvider(provider: string, model: string) {
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

export const WIZARD_STEPS = ["identity_seed", "infrastructure", "dropdown_mapping"];

export const AUTO_CERTIFY_SERVICES = [
  "llm",
  "plex",
  "radarr",
  "sonarr",
  "tmdb",
  "fanart",
  "tautulli",
  "seerr",
  "tunarr",
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

/** Knowledge-depth coverage (% overview, motifs, keywords, neighbors, loglines). */
export async function getLibraryKnowledgeCoverage(options: JsonObject = {}) {
  return api("/library/knowledge-coverage", options);
}

/** Owner demand list: titles opened to an empty More Like This / Related / bridge shelf. */
export async function getKinshipMissList({ limit = 50, signal }: JsonObject = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  return api(`/library/kinship-miss?${params}`, signal ? { signal } : {});
}

export async function getLibraryOverview() {
  return api("/library/overview");
}

export async function getLibraryAggregate(groupBy: string, { mediaType, topExamples }: JsonObject = {}) {
  const params = new URLSearchParams({ group_by: groupBy });
  if (mediaType === "movie" || mediaType === "show") params.set("media_type", mediaType);
  if (topExamples != null) params.set("top_examples", String(topExamples));
  return api(`/library/aggregate?${params}`);
}

export async function getLibraryHealth() {
  return api("/library/health");
}

export async function getExploreFeedRecentlyAddedEpisodes(
  {
  limit = 12,
  days = 30,
  offset = 0,
}: JsonObject = {},
) {
  const params = new URLSearchParams({
    limit: String(limit),
    days: String(days),
    offset: String(offset),
  });
  return api(`/library/feeds/recently-added-episodes?${params}`);
}

export async function getExploreFeedRecentlyAdded(
  {
  limit = 12,
  days = 30,
  offset = 0,
  mediaType,
}: JsonObject = {},
) {
  const params = new URLSearchParams({
    limit: String(limit),
    days: String(days),
    offset: String(offset),
  });
  if (mediaType) params.set("media_type", String(mediaType));
  return api(`/library/feeds/recently-added?${params}`);
}

export async function getExploreFeedRecentReleases(
  {
  limit = 12,
  days = 90,
  offset = 0,
  mediaType,
}: JsonObject = {},
) {
  const params = new URLSearchParams({
    limit: String(limit),
    days: String(days),
    offset: String(offset),
  });
  if (mediaType) params.set("media_type", String(mediaType));
  return api(`/library/feeds/recent-releases?${params}`);
}

export async function getExploreFeedOnThisDay({ limit = 12 }: JsonObject = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  return api(`/library/feeds/on-this-day?${params}`);
}

export async function getExploreFeedDirectorSpotlight({ limit = 12 }: JsonObject = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  return api(`/library/feeds/director-spotlight?${params}`);
}

export async function getExploreFeedGenreSpotlight({ limit = 12 }: JsonObject = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  return api(`/library/feeds/genre-spotlight?${params}`);
}

export async function getExploreFeedSeasonalSpotlight({ limit = 12 }: JsonObject = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  return api(`/library/feeds/seasonal-spotlight?${params}`);
}

export async function getExploreFeedRevisitThese({ limit = 20, idleDays = 60 }: JsonObject = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    idle_days: String(idleDays),
  });
  return api(`/library/feeds/revisit-these?${params}`);
}

export async function getExploreFeedContinueWatching({ limit = 12 }: JsonObject = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  return api(`/library/feeds/continue-watching?${params}`);
}

export async function getExploreFeedUnfinished({ limit = 12, idleDays = 60 }: JsonObject = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    idle_days: String(idleDays),
  });
  return api(`/library/feeds/unfinished?${params}`);
}

export async function getExploreFeedAfterglow({ limit = 12, days = 14 }: JsonObject = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    days: String(days),
  });
  return api(`/library/feeds/afterglow?${params}`);
}

export async function getExploreFeedTonightTable({ limit = 3 }: JsonObject = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  return api(`/library/feeds/tonight-table?${params}`);
}

export async function getExploreFeedForYou({ limit = 12 }: JsonObject = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  return api(`/library/feeds/for-you?${params}`);
}

export async function getLibraryMotifs({ limit = 160 }: JsonObject = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  return api(`/library/motifs?${params}`);
}

export async function getLibraryNeighbors(itemId: string | number, { mode = "similar", limit = 12 }: JsonObject = {}) {
  const params = new URLSearchParams({
    mode: String(mode || "similar"),
    limit: String(limit),
  });
  return api(`/library/neighbors/${encodeURIComponent(itemId)}?${params}`);
}

export async function getTitleRelations(
  mediaType: string,
  itemId: string | number,
  { idType = "tmdb", relation = "", limit = 50 }: JsonObject = {},
) {
  const params = new URLSearchParams({
    id_type: String(idType || "tmdb"),
    limit: String(limit),
  });
  if (relation) params.set("relation", String(relation));
  return api(
    `/title/${encodeURIComponent(mediaType)}/${encodeURIComponent(itemId)}/relations?${params}`,
  );
}

export async function walkTitleRelations(
  mediaType: string,
  itemId: string | number,
  { idType = "tmdb", relation = "", depth = 1, limit = 50 }: JsonObject = {},
) {
  const params = new URLSearchParams({
    id_type: String(idType || "tmdb"),
    depth: String(depth === 2 ? 2 : 1),
    limit: String(limit),
  });
  if (relation && relation !== "surprising") params.set("relation", String(relation));
  return api(
    `/title/${encodeURIComponent(mediaType)}/${encodeURIComponent(itemId)}/relations/walk?${params}`,
  );
}

export async function queryLibrary(filters: JsonObject = {}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value == null || value === "") continue;
    if (Array.isArray(value)) {
      const joined = value
        .map((v) => String(v).trim())
        .filter(Boolean)
        .join(",");
      if (joined) params.set(key, joined);
      continue;
    }
    params.set(key, String(value));
  }
  return api(`/library/query?${params}`);
}

/**
 * Search beyond the collection: TMDB titles de-duped against the library,
 * returned as acquisition-capable TitleCard-shaped items. Throws with
 * `error.status === 503` when external search is unavailable (e.g. TMDB not
 * configured) so callers can grey the affordance with a helpful note.
 */
export async function searchExternal({ q, mediaType = "movie", limit = 20 }: JsonObject = {}) {
  const params = new URLSearchParams();
  params.set("q", String(q || "").trim());
  if (mediaType) params.set("media_type", String(mediaType));
  params.set("limit", String(limit));
  return api(`/search/external?${params}`);
}

export async function getLibraryFacets(facetType: string, limit: number = 50, q: string = "") {
  const params = new URLSearchParams({
    facet_type: String(facetType || ""),
    limit: String(limit),
  });
  const query = String(q || "").trim();
  if (query) params.set("q", query);
  return api(`/library/facets?${params}`);
}

export async function getPerson(tmdbPersonId: string) {
  return api(`/person/${encodeURIComponent(tmdbPersonId)}`);
}

export async function resolvePerson(name: string) {
  const params = new URLSearchParams({ name: String(name || "").trim() });
  return api(`/person/resolve?${params}`);
}

export async function getPurgeCandidates() {
  return api("/library/purge-candidates");
}

export async function refreshPurgeCandidates(limit: number = 100) {
  const params = new URLSearchParams({ limit: String(limit) });
  return api(`/library/purge-candidates/refresh?${params}`, {
    method: "POST",
  });
}

/** Owner-only: refresh size/last-watched for visible purge rows. */
export async function enrichPurgeCandidates(ratingKeys: string[]) {
  return api("/library/purge-candidates/enrich", {
    method: "POST",
    body: JSON.stringify({ rating_keys: ratingKeys }),
  });
}

async function readRemovalNdjson(response: Response, onEvent?: (event: JsonObject) => void) {
  const reader = response.body?.getReader?.();
  if (!reader) {
    const payload = await response.json();
    onEvent?.({ type: "complete", result: payload });
    return payload;
  }
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult = null;
  const take = (line: JsParam) => {
    const trimmed = String(line || "").trim();
    if (!trimmed) return;
    const event = JSON.parse(trimmed);
    onEvent?.(event);
    if (event?.type === "complete") finalResult = event.result ?? null;
  };
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl = buffer.indexOf("\n");
    while (nl >= 0) {
      take(buffer.slice(0, nl));
      buffer = buffer.slice(nl + 1);
      nl = buffer.indexOf("\n");
    }
  }
  buffer += decoder.decode();
  if (buffer.trim()) take(buffer);
  return finalResult;
}

/** Stream per-title removal progress (NDJSON). One library lookup per title. */
async function streamLibraryRemoval(path: string, ratingKeys: string[], { mode, onEvent, signal, runId }: { mode?: string; onEvent?: (event: JsonObject) => void; signal?: AbortSignal; runId?: string } = {}) {
  const response = await fetch(`${API}${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", Accept: "application/x-ndjson" },
    body: JSON.stringify({
      rating_keys: ratingKeys,
      mode,
      stream: true,
      run_id: runId,
    }),
    signal,
  });
  if (!response.ok) {
    const text = await response.text();
    throwApiError(text, response.statusText, response.status);
  }
  return readRemovalNdjson(response, onEvent);
}

/** Ask a streamed removal to skip titles that have not started. */
export async function cancelLibraryRemoval(runId: string) {
  return api("/library/items/delete/cancel", {
    method: "POST",
    body: JSON.stringify({ run_id: runId }),
  });
}

/** Owner-only: delete purge candidates. Default ``mode: "full"`` (*arr + Plex + index).
 * Pass ``mode: "index"`` for undoable index-only prune.
 * Pass ``onEvent`` to stream per-title progress.
 */
export async function deletePurgeCandidates(ratingKeys: string[], { mode = "full", onEvent, signal, runId }: { mode?: string; onEvent?: (event: JsonObject) => void; signal?: AbortSignal; runId?: string } = {}) {
  if (onEvent || runId) {
    return streamLibraryRemoval("/library/purge-candidates/delete", ratingKeys, {
      mode,
      onEvent,
      signal,
      runId,
    });
  }
  return api("/library/purge-candidates/delete", {
    method: "POST",
    body: JSON.stringify({ rating_keys: ratingKeys, mode }),
  });
}

/** Owner-only: remove Projectionist library index rows by rating_key.
 * Pass ``mode: "full"`` to also delete via *arr (files + exclusion) and Plex.
 * Pass ``onEvent`` to stream per-title progress instead of one batch response.
 */
export async function deleteLibraryItems(ratingKeys: string[], { mode = "index", onEvent, signal, runId }: { mode?: string; onEvent?: (event: JsonObject) => void; signal?: AbortSignal; runId?: string } = {}) {
  if (onEvent || runId) {
    return streamLibraryRemoval("/library/items/delete", ratingKeys, {
      mode,
      onEvent,
      signal,
      runId,
    });
  }
  return api("/library/items/delete", {
    method: "POST",
    body: JSON.stringify({ rating_keys: ratingKeys, mode }),
  });
}

/** Owner-only: delete bad file(s) in *arr and search for replacements (no exclusion). */
export async function markBadMedia(payload: JsonObject) {
  return api("/library/items/mark-bad-media", {
    method: "POST",
    body: JSON.stringify({ confirm: true, ...(payload || {}) }),
  });
}

/** Mark an in-library title watched/unwatched (updates Projectionist + Plex when configured). */
export async function setLibraryItemWatched(ratingKey: string, watched: boolean = true) {
  return api("/library/items/watched", {
    method: "POST",
    body: JSON.stringify({ rating_key: ratingKey, watched: Boolean(watched) }),
  });
}

export async function dismissPurgeCandidates(ratingKeys: string[]) {
  return api("/library/purge-candidates/dismiss", {
    method: "POST",
    body: JSON.stringify({ rating_keys: ratingKeys }),
  });
}

export async function getTvProgress() {
  return api("/library/tv/progress");
}

/** Current signed-in user's tracker-backed summary for a movie or episode. */
export async function getWatchSummary(ratingKey: string) {
  return api(`/watch-tracker/summary/${encodeURIComponent(ratingKey)}`);
}

/** Current signed-in user's episode-first rollup for a show. */
export async function getShowWatchSummary(ratingKey: string) {
  return api(`/watch-tracker/shows/${encodeURIComponent(ratingKey)}/summary`);
}

/** Seasons + nested episodes for a library show (title detail). */
export async function getShowSeasons(
  {
  showId = null,
  tmdbId = null,
  tvdbId = null,
  show = "",
}: JsonObject = {},
) {
  const params = new URLSearchParams();
  if (showId != null && showId !== "") params.set("show_id", String(showId));
  if (tmdbId != null && tmdbId !== "") params.set("tmdb_id", String(tmdbId));
  if (tvdbId != null && tvdbId !== "") params.set("tvdb_id", String(tvdbId));
  if (show) params.set("show", String(show));
  const qs = params.toString();
  return api(`/library/tv/seasons${qs ? `?${qs}` : ""}`);
}

/** Single episode detail (show context + prev/next) for `/title/episode/:ratingKey`. */
export async function getLibraryEpisode(ratingKey: string) {
  const key = String(ratingKey || "").trim();
  if (!key) return Promise.reject(new Error("Missing episode key"));
  return api(`/library/tv/episode/${encodeURIComponent(key)}`);
}

/** Owner season/episode remove via Sonarr episode files + Plex + index. */
export async function removeTvScope(body: JsonObject) {
  return api("/library/tv/remove", {
    method: "POST",
    body: JSON.stringify(body || {}),
  });
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

export async function getAskDeleteConfirmation() {
  return api("/settings/ask-delete-confirmation");
}

export async function saveAskDeleteConfirmation(askDeleteConfirmation: JsonObject) {
  return api("/settings/ask-delete-confirmation", {
    method: "PUT",
    body: JSON.stringify({ ask_delete_confirmation: Boolean(askDeleteConfirmation) }),
  });
}

export async function saveSettings(payload: JsonObject) {
  return api("/settings", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

/** Owner-only: fetch one stored connection secret for in-place Show. Never log the value. */
export async function revealSettingsSecret(field: string) {
  return api("/settings/secrets/reveal", {
    method: "POST",
    body: JSON.stringify({ field }),
  });
}

export async function rotateMcpKey(which: string) {
  return api("/settings/mcp-keys/rotate", {
    method: "POST",
    body: JSON.stringify({ which }),
  });
}

export async function clearMcpKey(which: string) {
  return api("/settings/mcp-keys/clear", {
    method: "POST",
    body: JSON.stringify({ which }),
  });
}

export async function testService(service: string, settings: JsonObject) {
  const payload = {
    ...settings,
    seerr_url: settings?.seerr?.url ?? settings?.seerr_url ?? "",
    seerr_api_key: settings?.seerr?.api_key ?? settings?.seerr_api_key ?? "",
    tunarr_url: settings?.tunarr?.url ?? settings?.tunarr_url ?? "",
  };
  return api(`/setup/test/${service}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getLiveChannelsStatus() {
  return api("/admin/live-channels/status");
}

export async function postLiveChannelsPreflight(body: JsonObject = {}) {
  return api("/admin/live-channels/preflight", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function postLiveChannelsLifecycle(action = "ensure_running") {
  return api("/admin/live-channels/lifecycle", {
    method: "POST",
    body: JSON.stringify({ action }),
  });
}

export async function getLiveChannelsLifecycleStatus() {
  return api("/admin/live-channels/lifecycle-status");
}

export async function getLiveChannelsStarterPack() {
  return api("/admin/live-channels/starter-pack");
}

export async function publishLiveChannelsStarters(body: JsonObject = {}) {
  return api("/admin/live-channels/starters/publish", {
    method: "POST",
    body: JSON.stringify({
      confirm: true,
      wire_plex: true,
      fill_programming: true,
      ...body,
    }),
  });
}

export async function getLiveChannelsCraftOptions() {
  return api("/admin/live-channels/craft-options");
}

export async function previewLiveChannelsCraft(body: JsonObject = {}) {
  return api("/admin/live-channels/craft-preview", {
    method: "POST",
    body: JSON.stringify(body || {}),
  });
}

export async function patchLiveChannelsEngineSettings(body: JsonObject = {}) {
  return api("/admin/live-channels/engine-settings", {
    method: "PATCH",
    body: JSON.stringify({
      confirm: true,
      ...body,
    }),
  });
}

export async function publishLiveChannelsChannel(body: JsonObject = {}) {
  return api("/admin/live-channels/channels/publish", {
    method: "POST",
    body: JSON.stringify({
      confirm: true,
      wire_plex: true,
      fill_programming: true,
      ...body,
    }),
  });
}

export async function publishLiveChannelsFromCollection(body: JsonObject = {}) {
  return api("/admin/live-channels/channels/from-collection", {
    method: "POST",
    body: JSON.stringify({
      confirm: true,
      ...body,
    }),
  });
}

export async function publishLiveChannelsFromShow(body: JsonObject = {}) {
  return api("/admin/live-channels/channels/from-show", {
    method: "POST",
    body: JSON.stringify({
      confirm: true,
      ...body,
    }),
  });
}

export async function getLiveChannelsPublishStatus() {
  return api("/admin/live-channels/publish/status");
}

export async function refillLiveChannelsChannel(channelId: string, body: JsonObject = {}) {
  return api(`/admin/live-channels/channels/${encodeURIComponent(channelId)}/refill`, {
    method: "POST",
    body: JSON.stringify({
      confirm: true,
      ...body,
    }),
  });
}

export async function patchLiveChannelsStationSettings(channelId: string, body: JsonObject = {}) {
  return api(`/admin/live-channels/channels/${encodeURIComponent(channelId)}/settings`, {
    method: "PATCH",
    body: JSON.stringify({
      confirm: true,
      ...body,
    }),
  });
}

export async function getLiveChannelSubtitles(channelId: string) {
  return api(`/live-channels/channels/${encodeURIComponent(channelId)}/subtitles`);
}

export async function downloadLiveChannelSubtitles(channelId: string, body: JsonObject = {}) {
  return api(`/live-channels/channels/${encodeURIComponent(channelId)}/subtitles/download`, {
    method: "POST",
    body: JSON.stringify({
      confirm: true,
      ...body,
    }),
  });
}

export async function getLibraryItemSubtitles(ratingKey: string) {
  return api(`/library/items/${encodeURIComponent(ratingKey)}/subtitles`);
}

export async function downloadLibraryItemSubtitles(ratingKey: string, body: JsonObject = {}) {
  return api(`/library/items/${encodeURIComponent(ratingKey)}/subtitles/download`, {
    method: "POST",
    body: JSON.stringify({
      confirm: true,
      ...body,
    }),
  });
}

export async function postLiveChannelsContinuityRepair(body: JsonObject = {}) {
  return api("/admin/live-channels/continuity/repair", {
    method: "POST",
    body: JSON.stringify({
      confirm: true,
      rescan: true,
      repair: true,
      refill_lineups: true,
      ...body,
    }),
  });
}

export async function getLiveChannelsContinuityStatus() {
  return api("/admin/live-channels/continuity/status");
}

export async function deleteLiveChannelsChannel(channelId: string) {
  return api(`/admin/live-channels/channels/${encodeURIComponent(channelId)}`, {
    method: "DELETE",
  });
}

export async function getLiveChannelsPlexAttach() {
  return api("/admin/live-channels/plex-attach");
}

export async function postLiveChannelsPlexAttachGuide() {
  return api("/admin/live-channels/plex-attach-guide", { method: "POST", body: "{}" });
}

export async function postLiveChannelsPlexRepair() {
  return api("/admin/live-channels/plex-repair", { method: "POST", body: "{}" });
}

export async function getLiveChannelsTunarrLogs(lines: number = 200) {
  const limit = Math.max(1, Math.min(Number(lines) || 200, 2000));
  return api(`/admin/live-channels/tunarr-logs?lines=${limit}`);
}

export async function listRequests(params: QueryParams = {}) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return api(`/requests${query ? `?${query}` : ""}`);
}

export async function proposeAction(body: JsonObject) {
  return api("/actions/propose", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function confirmAction(token: string, confirmed = true) {
  return api("/actions/confirm", {
    method: "POST",
    body: JSON.stringify({ token, confirmed }),
  });
}

export async function listScheduledTasks() {
  return api("/admin/scheduled-tasks");
}

export async function optimizeScheduledTaskRates({ dry_run = false }: JsonObject = {}) {
  const search = new URLSearchParams();
  if (dry_run) search.set("dry_run", "true");
  const query = search.toString() ? `?${search}` : "";
  return api(`/admin/scheduled-tasks/optimize-rates${query}`, {
    method: "POST",
  });
}

export async function runScheduledTask(name: string, { wait = false }: JsonObject = {}) {
  const query = wait ? "?wait=true" : "";
  return api(`/admin/scheduled-tasks/${encodeURIComponent(name)}/run${query}`, {
    method: "POST",
  });
}

export async function updateScheduledTask(name: string, payload: JsonObject) {
  return api(`/admin/scheduled-tasks/${encodeURIComponent(name)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function resetScheduledTaskQuarantine(name: string) {
  return api(`/admin/scheduled-tasks/${encodeURIComponent(name)}/reset`, {
    method: "POST",
  });
}

export async function getScheduledTaskLog(name: string, { after_seq = 0, limit = 200 }: JsonObject = {}) {
  const search = new URLSearchParams({
    after_seq: String(after_seq || 0),
    limit: String(limit || 200),
  });
  return api(`/admin/scheduled-tasks/${encodeURIComponent(name)}/log?${search}`);
}

export async function getScheduledTaskHistory(name: string, { limit = 50 }: JsonObject = {}) {
  const search = new URLSearchParams({ limit: String(limit || 50) });
  return api(`/admin/scheduled-tasks/${encodeURIComponent(name)}/history?${search}`);
}

export async function getAllScheduledTaskHistory({ limit = 100 }: JsonObject = {}) {
  const search = new URLSearchParams({ limit: String(limit || 100) });
  return api(`/admin/scheduled-tasks-history?${search}`);
}

export async function getScheduledTaskRate(name: string, { lookback_hours = 72 }: JsonObject = {}) {
  const search = new URLSearchParams({
    lookback_hours: String(lookback_hours || 72),
  });
  return api(`/admin/scheduled-tasks/${encodeURIComponent(name)}/rate?${search}`);
}

export async function getLlmUsage({ days = 7, model, purpose, persona_id }: JsonObject = {}) {
  const search = new URLSearchParams({ days: String(days || 7) });
  if (model) search.set("model", model);
  if (purpose) search.set("purpose", purpose);
  if (persona_id) search.set("persona_id", persona_id);
  return api(`/admin/llm/usage?${search}`);
}

export async function getLlmModelCatalog() {
  return api("/admin/llm/models");
}

export async function listHolidays() {
  return api("/admin/holidays");
}

export async function createHoliday(payload: JsonObject) {
  return api("/admin/holidays", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateHoliday(observanceId: string, payload: JsonObject) {
  return api(`/admin/holidays/${encodeURIComponent(observanceId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteHoliday(observanceId: string) {
  return api(`/admin/holidays/${encodeURIComponent(observanceId)}`, {
    method: "DELETE",
  });
}

export async function restoreHolidayDefaults() {
  return api("/admin/holidays/restore-defaults", { method: "POST" });
}

export async function getHolidayRail(observanceId: string) {
  return api(`/admin/holidays/${encodeURIComponent(observanceId)}/rail`);
}

export async function setHolidayRailTitle(observanceId: string, payload: JsonObject) {
  return api(`/admin/holidays/${encodeURIComponent(observanceId)}/rail/titles`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function clearHolidayRailTitle(observanceId: string, libraryItemId: string) {
  return api(
    `/admin/holidays/${encodeURIComponent(observanceId)}/rail/titles/${encodeURIComponent(libraryItemId)}`,
    { method: "DELETE" },
  );
}

export async function searchHolidayLibrary(q: string, { limit = 12 }: JsonObject = {}) {
  const search = new URLSearchParams({ q: q || "", limit: String(limit || 12) });
  return api(`/admin/holidays-library-search?${search}`);
}

export async function refreshHolidaySchedule() {
  return api("/admin/holidays-schedule/refresh", { method: "POST" });
}

/** Owner: order a seasonal shelf — pins these titles to the front, in this order. */
export async function setHolidayRailOrder(observanceId: string, libraryItemIds: string[]) {
  return api(`/admin/holidays/${encodeURIComponent(observanceId)}/rail/order`, {
    method: "PUT",
    body: JSON.stringify({ library_item_ids: libraryItemIds }),
  });
}

/** Owner: ask the professor to propose seasonal shelf picks + staff-pick notes. */
export async function proposeHolidayRailCuration(observanceId: string, { limit = 10 }: JsonObject = {}) {
  return api(`/admin/holidays/${encodeURIComponent(observanceId)}/rail/curate`, {
    method: "POST",
    body: JSON.stringify({ limit }),
  });
}

/** Owner: confirm a professor proposal (replaces shelf order + notes). */
export async function applyHolidayRailCuration(observanceId: string, picks: JsonObject[]) {
  return api(`/admin/holidays/${encodeURIComponent(observanceId)}/rail/curate/apply`, {
    method: "POST",
    body: JSON.stringify({ picks }),
  });
}

/** Owner: save a staff-pick curator note for one shelf title. */
export async function setHolidayRailCuratorNote(observanceId: string, libraryItemId: string, curatorNote: string) {
  return api(
    `/admin/holidays/${encodeURIComponent(observanceId)}/rail/titles/${encodeURIComponent(libraryItemId)}/note`,
    {
      method: "PATCH",
      body: JSON.stringify({ curator_note: curatorNote ?? "" }),
    },
  );
}

/** Owner: weekly household letter — toggles + this week's text. */
export async function getWeeklyLetter() {
  return api("/admin/weekly-letter");
}

export async function saveWeeklyLetterSettings(payload: JsonObject) {
  return api("/admin/weekly-letter", {
    method: "PUT",
    body: JSON.stringify(payload || {}),
  });
}

export async function sendWeeklyLetterNow() {
  return api("/admin/weekly-letter/send", { method: "POST" });
}


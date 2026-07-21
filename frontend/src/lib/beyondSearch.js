/**
 * "Search beyond the collection" presentation helpers.
 *
 * Pure logic for the Explore browse affordance that queries TMDB for titles
 * NOT in the library and lets users acquire them. Keeping the gating, status,
 * copy, and de-dupe rules here (rather than inline in the page) makes them
 * unit-testable and consistent across light/dark themes.
 */

import { turnstyleItemCount } from "./turnstyleItems.js";

/** Title shown on the turnstyle overlay opened from the Beyond section. */
export const BEYOND_TURNSTYLE_TITLE = "Beyond your collection";

export const BEYOND_STATUS = {
  idle: "idle",
  loading: "loading",
  loaded: "loaded",
  empty: "empty",
  error: "error",
  unavailable: "unavailable",
};

/**
 * The affordance only makes sense with an active search query, and is hidden
 * once external search is known to be unavailable (TMDB not configured).
 */
export function shouldShowBeyondAffordance({ q, unavailable = false } = {}) {
  if (unavailable) return false;
  return Boolean(String(q || "").trim());
}

/** Prominent in the zero-results empty state; secondary when library results exist. */
export function beyondAffordancePlacement({ hasLibraryResults = false } = {}) {
  return hasLibraryResults ? "secondary" : "prominent";
}

/** The endpoint returns 503 when external search can't run (e.g. TMDB not configured). */
export function isTmdbUnavailableError(error) {
  return Number(error?.status) === 503;
}

/** Normalize the endpoint payload into a stable shape for rendering. */
export function normalizeExternalResults(payload) {
  const items = Array.isArray(payload?.items) ? payload.items : [];
  return {
    items,
    total: Number(payload?.total_matched ?? items.length) || 0,
    returned: Number(payload?.returned ?? items.length) || items.length,
    query: String(payload?.query || ""),
  };
}

/** Map a successful fetch to loaded (has hits) or empty (no hits). */
export function beyondStatusForResult(payload) {
  return normalizeExternalResults(payload).items.length
    ? BEYOND_STATUS.loaded
    : BEYOND_STATUS.empty;
}

/** Map a failed fetch to unavailable (503) or a generic error. */
export function beyondStatusForError(error) {
  return isTmdbUnavailableError(error) ? BEYOND_STATUS.unavailable : BEYOND_STATUS.error;
}

export function beyondCtaLabel({ q } = {}) {
  const query = String(q || "").trim();
  return query ? `Search beyond your collection for “${query}”` : "Search beyond your collection";
}

export function beyondSectionSubtitle({ q } = {}) {
  const query = String(q || "").trim();
  return query
    ? `Titles matching “${query}” that aren’t in your library yet`
    : "Titles that aren’t in your library yet";
}

export function beyondEmptyMessage({ q } = {}) {
  const query = String(q || "").trim();
  return query
    ? `Nothing beyond your collection matched “${query}”.`
    : "Nothing beyond your collection matched.";
}

export function beyondUnavailableNote() {
  return "Searching beyond your collection isn’t available right now. Ask the owner to connect a metadata source.";
}

export function beyondErrorNote() {
  return "Couldn’t search beyond your collection just now. Give it another try in a moment.";
}

/** Suppress add/request for titles already owned or queued — badge them instead. */
export function isBeyondItemAcquirable(item) {
  return Boolean(
    item &&
      !item.in_library &&
      !item.already_queued &&
      !item.in_radarr &&
      !item.in_sonarr,
  );
}

/** Badge shown on a beyond result, mirroring TitleCard's own badge logic. */
export function beyondItemBadge(item) {
  if (item?.in_library) return "In library";
  if (item?.already_queued || item?.in_radarr || item?.in_sonarr) return "In queue";
  return "New";
}

/**
 * Whether to show acquire (add/request) controls for a beyond result given the
 * viewer's capability. Guests (no add/request) get info-only; owned/queued
 * titles are suppressed for everyone.
 */
export function beyondItemShowsAcquire(item, capability) {
  return isBeyondItemAcquirable(item) && Boolean(capability?.canAdd || capability?.canRequest);
}

/**
 * Decide whether a poster-list search section should offer the
 * "Expand N titles in turnstyle view" control, and with what count/title.
 *
 * Mirrors the chat affordance exactly: only displayable cards are counted
 * (`turnstyleItemCount`), the control is hidden when nothing displayable is
 * present, and the label wording matches ChatThread's expand button so the two
 * surfaces stay consistent. The returned `title` is what the overlay header
 * shows and defaults to the "Beyond your collection" section name.
 */
export function beyondTurnstyleExpand(items = [], { title = BEYOND_TURNSTYLE_TITLE } = {}) {
  const count = turnstyleItemCount(items);
  return {
    show: count > 0,
    count,
    title,
    label: `Expand ${count} titles in turnstyle view`,
  };
}

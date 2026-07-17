/** Owner bulk-delete helpers for CuratorX library index records (not Plex files). */

import { normalizeUserRole } from "./addActions.js";

export const BULK_DELETE_CONFIRM_PHRASE = "DELETE";

/** location.state key for post-delete success feedback after navigating away. */
export const LIBRARY_DELETE_NOTICE_KEY = "libraryDeleteNotice";

export const EXPLORE_SECTION_TOOLBAR_LAYOUT = {
  containerClass: "explore-section-toolbar",
  /** Must match reading-column containment used by hero/results/pagination. */
  widthRule: "min(var(--reading-column-max, 72rem), 100%)",
  overflowRule: "clip",
};

export function libraryItemRatingKey(item) {
  const key = item?.rating_key ?? item?.plex_rating_key;
  const text = key == null ? "" : String(key).trim();
  return text;
}

/**
 * Library-index deletable: has a stable rating_key and is not an explicit
 * non-library / TMDB-only card.
 */
export function canBulkDeleteLibraryItem(item) {
  if (!item || typeof item !== "object") return false;
  if (!libraryItemRatingKey(item)) return false;
  if (item.in_library === false) return false;
  return true;
}

/**
 * Owner-only delete affordance for a single title (detail page CTA).
 * Single-user mode is treated as owner.
 */
export function canOwnerDeleteLibraryTitle(item, { role, multiUserEnabled = true } = {}) {
  const normalized = normalizeUserRole(role, { multiUserEnabled });
  if (normalized !== "owner") return false;
  return canBulkDeleteLibraryItem(item);
}

export function libraryDeleteNoticeFromState(locationState) {
  const msg = locationState?.[LIBRARY_DELETE_NOTICE_KEY];
  const text = typeof msg === "string" ? msg.trim() : "";
  return text;
}

export function formatLibraryDeleteSuccessMessage({ deleted = 0, title = "" } = {}) {
  const count = Number(deleted) || 0;
  const label = String(title || "").trim() || "title";
  if (count > 0) {
    return `Removed "${label}" from the CuratorX library index.`;
  }
  return `No matching library record for "${label}".`;
}

export function partitionBulkDeleteSelection(items, selectedKeys, itemKeyFn) {
  const list = Array.isArray(items) ? items : [];
  const selected = new Set(selectedKeys || []);
  const keyOf = typeof itemKeyFn === "function" ? itemKeyFn : (item) => libraryItemRatingKey(item);
  const chosen = list.filter((item) => selected.has(keyOf(item)));
  const deletable = chosen.filter(canBulkDeleteLibraryItem);
  const unavailable = chosen.filter((item) => !canBulkDeleteLibraryItem(item));
  return {
    selected: chosen,
    deletable,
    unavailable,
    ratingKeys: deletable.map(libraryItemRatingKey),
    titles: deletable.map((item) => String(item?.title || "Untitled").trim() || "Untitled"),
  };
}

export function isBulkDeleteConfirmPhrase(value) {
  return String(value || "").trim() === BULK_DELETE_CONFIRM_PHRASE;
}

export function formatBulkDeletePreviewTitles(titles, limit = 5) {
  const list = (Array.isArray(titles) ? titles : [])
    .map((title) => String(title || "").trim())
    .filter(Boolean);
  const capped = Math.max(0, Number(limit) || 0);
  const shown = capped ? list.slice(0, capped) : list;
  const remaining = Math.max(0, list.length - shown.length);
  return { shown, remaining, total: list.length };
}

/** CSS fragment expectations for the contained explore-section toolbar. */
export function exploreSectionToolbarLayoutMatchers() {
  return {
    container: /\.explore-section-toolbar\s*\{[^}]*width:\s*min\(var\(--reading-column-max/s,
    overflow: /\.explore-section-toolbar\s*\{[^}]*overflow-x:\s*clip/s,
    sortSelect: /\.explore-section-sort select\s*\{[^}]*border:\s*1px solid var\(--border/s,
    bulkWrap: /\.explore-section-bulk\s*\{[^}]*flex-wrap:\s*wrap/s,
  };
}

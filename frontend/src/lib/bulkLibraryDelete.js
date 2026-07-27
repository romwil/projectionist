/** Owner bulk-delete helpers for Projectionist library index records (not Plex files). */

import { normalizeUserRole } from "./addActions.js";

export const BULK_DELETE_CONFIRM_PHRASE = "DELETE";

/** location.state key for post-delete success feedback after navigating away. */
export const LIBRARY_DELETE_NOTICE_KEY = "libraryDeleteNotice";

export const LIBRARY_DELETE_MODE_INDEX = "index";
export const LIBRARY_DELETE_MODE_FULL = "full";

export const EXPLORE_SECTION_TOOLBAR_LAYOUT = {
  containerClass: "explore-section-toolbar",
  /** Must match reading-column containment used by hero/results/pagination. */
  widthRule: "min(var(--reading-column-max, 72rem), 100%)",
  overflowRule: "clip",
};

export function normalizeLibraryDeleteMode(value) {
  const mode = String(value || LIBRARY_DELETE_MODE_INDEX).trim().toLowerCase();
  return mode === LIBRARY_DELETE_MODE_FULL ? LIBRARY_DELETE_MODE_FULL : LIBRARY_DELETE_MODE_INDEX;
}

export function libraryDeleteModeLabel(mode) {
  return normalizeLibraryDeleteMode(mode) === LIBRARY_DELETE_MODE_FULL
    ? "Fully remove"
    : "Delete from library";
}

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

export function formatLibraryDeleteSuccessMessage({
  deleted = 0,
  title = "",
  mode = LIBRARY_DELETE_MODE_INDEX,
  errorCount = 0,
} = {}) {
  const count = Number(deleted) || 0;
  const failures = Number(errorCount) || 0;
  const label = String(title || "").trim() || "title";
  const full = normalizeLibraryDeleteMode(mode) === LIBRARY_DELETE_MODE_FULL;
  if (full) {
    if (count > 0 && failures === 0) {
      return `Fully removed "${label}" (files via *arr, Plex entry, Projectionist index).`;
    }
    if (count > 0 && failures > 0) {
      return `Fully removed ${count} title${count === 1 ? "" : "s"}; ${failures} could not be fully removed.`;
    }
    if (failures > 0) {
      return `Could not fully remove "${label}". Check Radarr/Sonarr configuration and whether the title is managed there.`;
    }
    return `No matching library record for "${label}".`;
  }
  if (count > 0) {
    return `Removed "${label}" from the Projectionist library index.`;
  }
  return `No matching library record for "${label}".`;
}

export function formatBulkLibraryDeleteResultMessage(result, { titles = [] } = {}) {
  const mode = normalizeLibraryDeleteMode(result?.mode);
  const deleted = Number(result?.deleted) || 0;
  const errors = Array.isArray(result?.errors) ? result.errors : [];
  if (mode === LIBRARY_DELETE_MODE_FULL) {
    if (deleted > 0 && errors.length === 0) {
      return `Fully removed ${deleted} title${deleted === 1 ? "" : "s"} from the stack.`;
    }
    if (deleted > 0 && errors.length > 0) {
      const first = String(errors[0]?.error || "unknown error");
      return `Fully removed ${deleted}; ${errors.length} failed (${first}).`;
    }
    if (errors.length > 0) {
      return String(errors[0]?.error || "Full remove failed for the selected titles.");
    }
    return "No titles were fully removed.";
  }
  if (deleted === 1 && titles.length === 1) {
    return formatLibraryDeleteSuccessMessage({ deleted, title: titles[0], mode });
  }
  return `Removed ${deleted} title${deleted === 1 ? "" : "s"} from the Projectionist library index.`;
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
    overflow: /\.explore-section-toolbar\s*\{[^}]*overflow:\s*visible/s,
    sortSelect: /\.media-browse-filter-menu\s+>\s+summary\s*\{[^}]*border:\s*1px solid var\(--border/s,
    bulkWrap: /\.explore-section-bulk\s*\{[^}]*flex-wrap:\s*wrap/s,
  };
}

/** Owner bulk-delete helpers for Projectionist library index records (not Plex files). */

import { normalizeUserRole } from "./addActions.js";

export const BULK_DELETE_CONFIRM_PHRASE = "DELETE";

/** Shown when confirm is attempted with an empty deletable selection. */
export const BULK_DELETE_EMPTY_SELECTION_MESSAGE =
  "No titles selected. Cancel and select at least one title to continue.";

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

export function formatRemovalBytes(bytes) {
  const value = Number(bytes) || 0;
  if (value <= 0) return "0 B";
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${(value / 1024 ** 3).toFixed(2)} GB`;
}

/** Honest freed label — avoid implying measured 0 B when *arr had no size. */
export function formatRemovalFreedLabel(entryOrTotals) {
  const bytes = Number(entryOrTotals?.bytes_freed) || 0;
  const source = String(entryOrTotals?.bytes_source || "").trim().toLowerCase();
  const files = Array.isArray(entryOrTotals?.files)
    ? entryOrTotals.files.length
    : Number(entryOrTotals?.files) || 0;
  const folders = Array.isArray(entryOrTotals?.folders)
    ? entryOrTotals.folders.length
    : Number(entryOrTotals?.folders) || 0;

  if (source === "library_estimate" && bytes > 0) {
    return `~${formatRemovalBytes(bytes)} (est.)`;
  }
  if (bytes > 0) return formatRemovalBytes(bytes);
  if (source === "unknown" || (files === 0 && folders > 0)) {
    return "Size unknown";
  }
  return "0 B";
}

export function removalPathsNote(entry) {
  const note = String(entry?.note || "").trim();
  if (note) return note;
  const files = Array.isArray(entry?.files) ? entry.files : [];
  const folders = Array.isArray(entry?.folders) ? entry.folders : [];
  if (!files.length && folders.length) {
    return (
      "*arr reported the title folder but no episode file list. " +
      "Disk files may have been removed with the folder."
    );
  }
  if (!files.length) return "No file paths reported by *arr.";
  return "";
}

/** Prefer API totals including 0; only fall back when missing/non-finite. */
function coerceTotal(value, fallback) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export function normalizeRemovalSummary(result) {
  const results = Array.isArray(result?.results)
    ? result.results.map((entry) => ({
        rating_key: String(entry?.rating_key || ""),
        title: String(entry?.title || "Untitled").trim() || "Untitled",
        media_type: String(entry?.media_type || ""),
        files: Array.isArray(entry?.files) ? entry.files.map(String).filter(Boolean) : [],
        folders: Array.isArray(entry?.folders)
          ? entry.folders.map(String).filter(Boolean)
          : [],
        bytes_freed: Number(entry?.bytes_freed) || 0,
        bytes_source: String(entry?.bytes_source || "").trim() || "unknown",
        note: String(entry?.note || "").trim(),
        ok: Boolean(entry?.ok),
      }))
    : [];
  const totalsRaw = result?.totals && typeof result.totals === "object" ? result.totals : null;
  const totals = {
    files: coerceTotal(
      totalsRaw?.files,
      results.reduce((sum, entry) => sum + entry.files.length, 0),
    ),
    folders: coerceTotal(
      totalsRaw?.folders,
      results.reduce((sum, entry) => sum + entry.folders.length, 0),
    ),
    bytes_freed: coerceTotal(
      totalsRaw?.bytes_freed,
      results.reduce((sum, entry) => sum + (Number(entry.bytes_freed) || 0), 0),
    ),
  };
  const sources = new Set(results.map((entry) => entry.bytes_source).filter(Boolean));
  let bytes_source = "unknown";
  if (sources.size === 1) bytes_source = [...sources][0];
  else if (sources.has("arr") && totals.bytes_freed > 0) bytes_source = "arr";
  else if (sources.has("library_estimate")) bytes_source = "library_estimate";
  return {
    deleted: Number(result?.deleted) || 0,
    results,
    errors: Array.isArray(result?.errors) ? result.errors : [],
    totals: { ...totals, bytes_source, files: totals.files, folders: totals.folders },
  };
}

/** True when a full-remove payload has per-title or aggregate path/size detail. */
export function hasRemovalSummary(result) {
  if (normalizeLibraryDeleteMode(result?.mode) !== LIBRARY_DELETE_MODE_FULL) return false;
  const summary = normalizeRemovalSummary(result);
  if (summary.results.length > 0) return true;
  return (
    summary.totals.files > 0 ||
    summary.totals.folders > 0 ||
    summary.totals.bytes_freed > 0
  );
}

export function formatBulkLibraryDeleteResultMessage(result, { titles = [] } = {}) {
  const mode = normalizeLibraryDeleteMode(result?.mode);
  const deleted = Number(result?.deleted) || 0;
  const errors = Array.isArray(result?.errors) ? result.errors : [];
  if (mode === LIBRARY_DELETE_MODE_FULL) {
    const freed = Number(result?.totals?.bytes_freed) || 0;
    const freedSuffix = freed > 0 ? ` · ${formatRemovalBytes(freed)} freed` : "";
    if (deleted > 0 && errors.length === 0) {
      return `Fully removed ${deleted} title${deleted === 1 ? "" : "s"} from the stack${freedSuffix}.`;
    }
    if (deleted > 0 && errors.length > 0) {
      const first = String(errors[0]?.error || "unknown error");
      return `Fully removed ${deleted}; ${errors.length} failed (${first})${freedSuffix}.`;
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

import { exploreLanguagePath } from "./browseLinks.js";
import { formatLanguageName, normalizeLanguageCode } from "./languageNames.js";
import {
  buildMediaBrowseParams,
  isAllPageSize,
  queryFiltersFromBrowse,
  resolvePageSizeLimit,
} from "./mediaBrowse.js";

export const NO_MATCHING_TITLES = "No matching titles.";
export const ALL_LANGUAGES_HEADING = "All languages";
export const LANGUAGE_LANDING_LEDE = "Library titles in this original language";
export const ALL_LANGUAGES_LEDE = "Library titles in every original language";

/** Stored sentinels that are not a language on a title. */
const OMITTED_LANGUAGE_CODES = new Set(["und", "unknown", "zxx", "none", "null"]);

export function languageLandingCode(raw) {
  return normalizeLanguageCode(raw);
}

function normalizeLandingMediaType(raw) {
  const value = String(raw || "").trim().toLowerCase();
  if (value === "movie" || value === "movies") return "movie";
  if (value === "show" || value === "shows" || value === "tv") return "show";
  return "";
}

/**
 * Distinct original languages that occur on catalog titles.
 * Buckets come from `/api/library/aggregate?group_by=language` (SQL on
 * `original_language`). Empty and unknown sentinels are omitted. Codes that
 * are not in the buckets are not offered.
 */
export function languageOptionsFromBuckets(buckets = []) {
  const counts = new Map();
  for (const bucket of buckets || []) {
    const code = normalizeLanguageCode(bucket?.value ?? bucket?.language ?? "");
    if (!code || OMITTED_LANGUAGE_CODES.has(code)) continue;
    const count = Number(bucket?.count);
    counts.set(code, (counts.get(code) || 0) + (Number.isFinite(count) ? count : 0));
  }
  return [...counts.entries()]
    .map(([code, count]) => ({
      code,
      label: formatLanguageName(code),
      count,
    }))
    .sort((a, b) => a.label.localeCompare(b.label) || a.code.localeCompare(b.code));
}

/**
 * Library query for `/explore?language=`. A blank code is every original
 * language. A code always stays on the query so an unrecognized value cannot
 * widen into an unfiltered read.
 */
export function languageLandingRequest(rawCode, browse = {}) {
  const code = languageLandingCode(rawCode);
  const filters = queryFiltersFromBrowse(browse, code ? { original_language: code } : {});
  const mediaType = normalizeLandingMediaType(filters.media_type);
  if (mediaType) filters.media_type = mediaType;
  else delete filters.media_type;
  if (browse.year) {
    filters.year_from = browse.year;
    filters.year_to = browse.year;
    delete filters.year;
  }
  if (isAllPageSize(browse.limit)) {
    filters.limit = resolvePageSizeLimit("all");
    filters.offset = 0;
  }
  if (!code) delete filters.original_language;
  return { kind: "query", code, filters };
}

/** Keep the language facet on every toolbar update. Relative path only. */
export function buildLanguageLandingSearch(rawCode, browse, updates = {}) {
  const { language: languageUpdate, ...browseUpdates } = updates;
  const params = buildMediaBrowseParams(browse, browseUpdates);
  const code = Object.prototype.hasOwnProperty.call(updates, "language")
    ? languageLandingCode(languageUpdate)
    : languageLandingCode(rawCode);
  // Keep the key even when empty so clearing the filter stays on this page.
  params.set("language", code);
  return params;
}

export function languageLandingPath(rawCode) {
  return exploreLanguagePath(languageLandingCode(rawCode));
}

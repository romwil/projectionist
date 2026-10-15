import { exploreLanguagePath } from "./browseLinks.js";
import { isKnownLanguageCode, normalizeLanguageCode } from "./languageNames.js";
import {
  buildMediaBrowseParams,
  isAllPageSize,
  queryFiltersFromBrowse,
  resolvePageSizeLimit,
} from "./mediaBrowse.js";

export const NO_MATCHING_TITLES = "No matching titles.";
export const UNKNOWN_LANGUAGE = "That language code is not recognized.";

export const LANGUAGE_MEDIA_TABS = [
  { id: "all", label: "All", mediaType: "" },
  { id: "movie", label: "Movies", mediaType: "movie" },
  { id: "show", label: "TV", mediaType: "show" },
];

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
 * Library query for `/explore?language=`. Unknown codes never become an
 * unfiltered library read. A blank code is an empty result, not the hub.
 */
export function languageLandingRequest(rawCode, browse = {}) {
  const code = languageLandingCode(rawCode);
  if (!code) {
    return { kind: "empty", message: NO_MATCHING_TITLES };
  }
  if (!isKnownLanguageCode(code)) {
    return { kind: "unknown", code, message: UNKNOWN_LANGUAGE };
  }
  const filters = queryFiltersFromBrowse(browse, { original_language: code });
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
  if (!filters.original_language) {
    return { kind: "unknown", code, message: UNKNOWN_LANGUAGE };
  }
  return { kind: "query", code, filters };
}

/** Keep the language facet on every toolbar update. Relative path only. */
export function buildLanguageLandingSearch(rawCode, browse, updates = {}) {
  const nextCode = Object.hasOwn(updates, "language") ? updates.language : rawCode;
  const code = languageLandingCode(nextCode);
  const params = buildMediaBrowseParams(browse, { ...updates, language: code || "" });
  if (code) params.set("language", code);
  else params.delete("language");
  return params;
}

export function languageLandingPath(rawCode) {
  return exploreLanguagePath(languageLandingCode(rawCode));
}

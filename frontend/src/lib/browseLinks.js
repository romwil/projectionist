/** Path helpers for person and tag browse pages. */

import { ROUTES, withReturnTo } from "./backNav.js";

export { ROUTES, withReturnTo };

export function personPath(tmdbPersonId) {
  if (tmdbPersonId == null || tmdbPersonId === "") return null;
  const id = String(tmdbPersonId).trim();
  if (!id || Number.isNaN(Number(id))) return null;
  return `/person/${encodeURIComponent(id)}`;
}

export function tagPath(tagName) {
  const name = String(tagName || "").trim();
  if (!name) return null;
  return `/tag/${encodeURIComponent(name)}`;
}

export function exploreTagsPath() {
  return ROUTES.tags;
}

export function explorePlotLabPath() {
  return ROUTES.plotLab;
}

export function exploreGenrePath(genreName) {
  const name = String(genreName || "").trim();
  if (!name) return null;
  return `/explore?genre=${encodeURIComponent(name)}`;
}

export function exploreCastPath(name) {
  const cleaned = String(name || "").trim();
  if (!cleaned) return null;
  return `/explore?cast=${encodeURIComponent(cleaned)}`;
}

export function exploreDirectorsPath(name) {
  const cleaned = String(name || "").trim();
  if (!cleaned) return null;
  return `/explore?directors=${encodeURIComponent(cleaned)}`;
}

export function exploreDecadePath(decadeLabel) {
  const label = String(decadeLabel || "").trim();
  if (!/^\d{4}s$/.test(label)) return null;
  return `/explore?decade=${encodeURIComponent(label)}`;
}

export function exploreLanguagePath(languageCode) {
  const code = String(languageCode || "").trim().toLowerCase().split("-")[0];
  if (!code) return null;
  return `/explore?language=${encodeURIComponent(code)}`;
}

export function exploreCountryPath(countryName) {
  const name = String(countryName || "").trim();
  if (!name) return null;
  return `/explore?country=${encodeURIComponent(name)}`;
}

/** year_from / year_to for library query from a decade label like "2020s". */
export function decadeYearRange(decadeLabel) {
  const label = String(decadeLabel || "").trim();
  const match = /^(\d{4})s$/.exec(label);
  if (!match) return null;
  const start = Number(match[1]);
  if (!Number.isFinite(start)) return null;
  return { year_from: start, year_to: start + 9 };
}

/**
 * Deep-link to top-level Search (library + beyond). Pass `mediaType` (movie/show)
 * and/or a free-text `q` search; omit both for the full library.
 */
export function libraryBrowsePath({ mediaType, q } = {}) {
  const params = new URLSearchParams();
  if (mediaType === "movie" || mediaType === "show") {
    params.set("media_type", mediaType);
  }
  const query = String(q || "").trim();
  if (query) params.set("q", query);
  const search = params.toString();
  const base = ROUTES.search || ROUTES.libraryBrowse;
  return search ? `${base}?${search}` : base;
}

/** Drill-down path for an Explore hub section (e.g. recently-added). */
export function exploreSectionPath(sectionId, { mediaType, limit, offset } = {}) {
  const id = String(sectionId || "").trim();
  if (!id) return null;
  const params = new URLSearchParams();
  if (mediaType === "movie" || mediaType === "show") {
    params.set("media_type", mediaType);
  }
  if (limit != null && limit !== "") params.set("limit", String(limit));
  if (offset != null && Number(offset) > 0) params.set("offset", String(offset));
  const query = params.toString();
  const base = `/explore/section/${encodeURIComponent(id)}`;
  return query ? `${base}?${query}` : base;
}

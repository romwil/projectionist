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

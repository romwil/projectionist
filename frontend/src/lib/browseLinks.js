/** Path helpers for person and tag browse pages. */

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

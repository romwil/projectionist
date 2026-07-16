/** Helpers for concurrent per-card add tracking (no global gate). */

export function addItemKey(item, target = "") {
  const media = String(item?.media_type || "");
  const tmdb = item?.tmdb_id != null ? String(item.tmdb_id) : "";
  const tvdb = item?.tvdb_id != null ? String(item.tvdb_id) : "";
  const rating = item?.rating_key != null ? String(item.rating_key) : "";
  const title = String(item?.title || "").trim().toLowerCase();
  return `${media}:${tmdb}:${tvdb}:${rating}:${title}:${target || ""}`;
}

/** True when this card's own add is in flight — never blocks other cards. */
export function isAddBlockedForKey(inFlightKeys, key) {
  if (!key) return false;
  if (inFlightKeys instanceof Set) return inFlightKeys.has(key);
  if (Array.isArray(inFlightKeys)) return inFlightKeys.includes(key);
  return false;
}

export function withAddInFlight(inFlightKeys, key) {
  const next = new Set(inFlightKeys instanceof Set ? inFlightKeys : inFlightKeys || []);
  if (key) next.add(key);
  return next;
}

export function withoutAddInFlight(inFlightKeys, key) {
  const next = new Set(inFlightKeys instanceof Set ? inFlightKeys : inFlightKeys || []);
  if (key) next.delete(key);
  return next;
}

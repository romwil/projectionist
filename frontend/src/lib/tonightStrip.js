/** Normalize tonight / quick-pick payloads into a compact composer strip. */

export const TONIGHT_STRIP_LIMIT = 3;

export function normalizeTonightItems(payload, { limit = TONIGHT_STRIP_LIMIT } = {}) {
  const capped = Math.min(Math.max(1, Number(limit) || TONIGHT_STRIP_LIMIT), 3);
  const raw = Array.isArray(payload?.items)
    ? payload.items
    : payload?.item
      ? [payload.item]
      : [];
  const seen = new Set();
  const items = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const key = `${item.media_type || ""}:${item.tmdb_id || item.rating_key || item.title}`;
    if (seen.has(key)) continue;
    seen.add(key);
    items.push(item);
    if (items.length >= capped) break;
  }
  return items;
}

export function tonightStripVisible(items, { loading = false, dismissed = false } = {}) {
  if (dismissed) return false;
  if (loading) return true;
  return Array.isArray(items) && items.length > 0;
}

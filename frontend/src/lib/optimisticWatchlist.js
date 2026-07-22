/**
 * Optimistic watchlist pin helpers — update local list immediately, reconcile via API.
 */

import { watchlistItemKey } from "./watchlistKeys.js";

/** Build a temporary local pin before the server echoes one back. */
export function optimisticPinFromItem(item, { id } = {}) {
  const now = Date.now() / 1000;
  return {
    id: id || `optimistic-${watchlistItemKey(item)}-${Math.random().toString(36).slice(2, 8)}`,
    tmdb_id: item?.tmdb_id ?? null,
    tvdb_id: item?.tvdb_id ?? null,
    media_type: item?.media_type === "show" ? "show" : "movie",
    title: item?.title || "Unknown title",
    created_at: now,
    plex_rating_key: item?.plex_rating_key || item?.rating_key || null,
    _optimistic: true,
  };
}

/** Remove a pin from a list by id (immutable). */
export function removePinById(pins, pinId) {
  const id = String(pinId || "");
  if (!id) return Array.isArray(pins) ? pins.slice() : [];
  return (Array.isArray(pins) ? pins : []).filter((pin) => String(pin?.id) !== id);
}

/** Upsert a pin into a list keyed by media_type+ids (immutable). */
export function upsertPin(pins, pin) {
  const list = Array.isArray(pins) ? pins.slice() : [];
  if (!pin) return list;
  const key = watchlistItemKey(pin);
  const idx = list.findIndex((entry) => watchlistItemKey(entry) === key);
  if (idx >= 0) {
    list[idx] = { ...list[idx], ...pin };
  } else {
    list.unshift(pin);
  }
  return list;
}

/**
 * Apply an optimistic add or remove.
 * @returns {{ next: unknown[], rollback: unknown[] }}
 */
export function applyOptimisticPinToggle(pins, { item, pinRecord, adding }) {
  const previous = Array.isArray(pins) ? pins.slice() : [];
  if (!adding && pinRecord?.id) {
    return { next: removePinById(previous, pinRecord.id), rollback: previous };
  }
  const optimistic = optimisticPinFromItem(item, { id: pinRecord?.id });
  return { next: upsertPin(previous, optimistic), rollback: previous };
}

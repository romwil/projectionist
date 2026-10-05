/**
 * Session cache for Explore hub — stale-while-revalidate for snappy revisits.
 * Server also TTL-caches; this avoids a blank first paint when bouncing back
 * from chat/title detail within the same tab session.
 */

export const EXPLORE_HUB_CACHE_KEY = "projectionist.exploreHub.v1";
export const EXPLORE_HUB_CLIENT_TTL_MS = 60_000;

export function readExploreHubCache(storage = globalThis.sessionStorage) {
  if (!storage) return null;
  try {
    const raw = storage.getItem(EXPLORE_HUB_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || !parsed.payload) return null;
    const savedAt = Number(parsed.savedAt) || 0;
    const ageMs = Date.now() - savedAt;
    return {
      payload: parsed.payload,
      savedAt,
      stale: ageMs > EXPLORE_HUB_CLIENT_TTL_MS,
      ageMs,
    };
  } catch {
    return null;
  }
}

export function writeExploreHubCache(payload, storage = globalThis.sessionStorage) {
  if (!storage || !payload || typeof payload !== "object") return;
  try {
    storage.setItem(EXPLORE_HUB_CACHE_KEY, JSON.stringify({ savedAt: Date.now(), payload }));
  } catch {
    // sessionStorage unavailable / quota
  }
}

export function clearExploreHubCache(storage = globalThis.sessionStorage) {
  if (!storage) return;
  try {
    storage.removeItem(EXPLORE_HUB_CACHE_KEY);
  } catch {
    // ignore
  }
}

/**
 * A hub response is still filling in when the server says so.
 * Partial rails (some posters already present) must keep polling — stopping
 * at the first non-empty payload is what left the slow rails blank.
 */
export function exploreHubStillWarming(payload) {
  return Boolean(payload?.warming);
}

/** Normalize a hub rail into the shape ExplorePage rails expect. */
export function hubRailState(hubPayload, railKey, { loading = false, error = "" } = {}) {
  const rail = hubPayload?.rails?.[railKey];
  if (!rail || typeof rail !== "object") {
    return {
      loading: loading || exploreHubStillWarming(hubPayload),
      items: [],
      note: null,
      error,
      meta: {},
    };
  }
  const items = Array.isArray(rail.items) ? rail.items : [];
  // `pending` is explicit and only while the hub is still warming. An empty
  // finished rail (no flag, or warming already cleared) is a real empty.
  const pending = items.length === 0 && rail.pending === true && exploreHubStillWarming(hubPayload);
  const meta = Object.fromEntries(
    Object.entries(rail).filter(([key]) => key !== "items" && key !== "note" && key !== "pending"),
  );
  return {
    loading: pending || (loading && !hubPayload),
    items,
    note: pending
      ? null
      : typeof rail.note === "string" && rail.note.trim()
        ? rail.note.trim()
        : null,
    error: pending ? "" : error,
    meta,
  };
}

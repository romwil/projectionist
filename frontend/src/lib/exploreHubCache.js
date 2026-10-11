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
    storage.removeItem(CONTINUE_WATCHING_PROGRESS_KEY);
  } catch {
    // ignore
  }
}

/** In-app play progress waiting to land on the Continue Watching rail. */
export const CONTINUE_WATCHING_PROGRESS_KEY = "projectionist.continueWatchingProgress.v1";
export const CONTINUE_WATCHING_PROGRESS_EVENT = "projectionist-continue-watching";
const CONTINUE_WATCHING_PROGRESS_TTL_MS = 15 * 60 * 1000;

function readProgressNotes(storage) {
  if (!storage) return [];
  try {
    const parsed = JSON.parse(storage.getItem(CONTINUE_WATCHING_PROGRESS_KEY) || "[]");
    if (!Array.isArray(parsed)) return [];
    const now = Date.now();
    return parsed.filter((note) => note && now - (Number(note.at) || 0) < CONTINUE_WATCHING_PROGRESS_TTL_MS);
  } catch {
    return [];
  }
}

function writeProgressNotes(notes, storage) {
  if (!storage) return;
  try {
    storage.setItem(CONTINUE_WATCHING_PROGRESS_KEY, JSON.stringify(notes));
  } catch {
    // sessionStorage unavailable / quota
  }
}

export function continueWatchingResumeLabel({
  mediaType = "",
  viewOffsetMs = 0,
  durationMs = 0,
  season = null,
  episode = null,
  episodeTitle = "",
} = {}) {
  const parts = [];
  if (mediaType === "episode" || season != null || episode != null) {
    if (season != null && episode != null) parts.push(`S${Number(season)}E${Number(episode)}`);
    else if (episodeTitle) parts.push(episodeTitle);
  }
  const offset = Number(viewOffsetMs) || 0;
  const duration = Number(durationMs) || 0;
  if (offset > 0 && duration > 0) {
    const pct = Math.min(99, Math.max(1, Math.round((100 * offset) / duration)));
    parts.push(`${pct}% watched`);
  } else if (offset > 0) {
    parts.push(`Resume at ${Math.max(1, Math.round(offset / 60000))}m`);
  } else {
    parts.push("Resume");
  }
  return parts.join(" · ");
}

function progressMatchesItem(item, ratingKey) {
  return item?.play_rating_key === ratingKey || item?.rating_key === ratingKey;
}

/**
 * Splice one in-app play into a hub payload's Continue Watching rail.
 * A finished play drops the title. A new offset replaces the previous row.
 */
export function applyContinueWatchingProgress(payload, progress) {
  if (!payload || typeof payload !== "object" || !progress?.ratingKey) return payload;
  const ratingKey = String(progress.ratingKey);
  const offset = Math.max(0, Math.floor(Number(progress.viewOffsetMs) || 0));
  const duration = Math.max(0, Math.floor(Number(progress.durationMs) || 0));
  const finished = Boolean(progress.finished) || offset <= 0;
  const rails = payload.rails && typeof payload.rails === "object" ? payload.rails : {};
  const rail = rails.continue_watching && typeof rails.continue_watching === "object"
    ? rails.continue_watching
    : { feed: "continue-watching", items: [], total: 0, note: null };
  let items = Array.isArray(rail.items) ? rail.items.filter((item) => item && typeof item === "object") : [];
  items = items.filter((item) => !progressMatchesItem(item, ratingKey));
  if (!finished) {
    const mediaType = progress.mediaType === "episode" ? "episode" : progress.mediaType || "movie";
    items = [
      {
        rating_key: ratingKey,
        play_rating_key: ratingKey,
        title: progress.title || "Untitled",
        year: progress.year || null,
        media_type: mediaType === "episode" ? "show" : mediaType,
        poster_url: progress.posterUrl || "",
        in_library: true,
        card_kind: "continue_watching",
        watch_state: "partial",
        view_offset_ms: offset,
        duration_ms: duration || null,
        resume_label: continueWatchingResumeLabel({
          mediaType,
          viewOffsetMs: offset,
          durationMs: duration,
          season: progress.season,
          episode: progress.episode,
          episodeTitle: progress.episodeTitle,
        }),
        ...(mediaType === "episode"
          ? {
              continue_episode_title: progress.episodeTitle || "",
              continue_season: progress.season ?? null,
              continue_episode: progress.episode ?? null,
            }
          : {}),
      },
      ...items,
    ];
  }
  const note = items.length
    ? null
    : typeof rail.note === "string" && rail.note.trim()
      ? rail.note
      : "Nothing in progress — start something in Plex, or wait for watch progress to sync.";
  return {
    ...payload,
    rails: {
      ...rails,
      continue_watching: {
        ...rail,
        items,
        total: items.length,
        note,
        pending: false,
      },
    },
  };
}

function railMatchesProgress(payload, progress) {
  const items = payload?.rails?.continue_watching?.items;
  const list = Array.isArray(items) ? items : [];
  const found = list.find((item) => progressMatchesItem(item, String(progress.ratingKey)));
  if (progress.finished || Number(progress.viewOffsetMs) <= 0) return !found;
  return Number(found?.view_offset_ms) === Math.floor(Number(progress.viewOffsetMs) || 0);
}

/**
 * Keep a play the app just recorded when a hub response is still the old snapshot.
 * Notes stay until they expire so a later stale on-deck row cannot paint over them.
 * When the payload already has that offset, the server card is left as-is.
 */
export function mergeContinueWatchingNotes(payload, storage = globalThis.sessionStorage) {
  const notes = readProgressNotes(storage);
  if (!payload || !notes.length) return payload;
  let next = payload;
  for (const note of notes) {
    if (railMatchesProgress(next, note)) continue;
    next = applyContinueWatchingProgress(next, note);
  }
  return next;
}

export function rememberContinueWatchingProgress(progress, storage = globalThis.sessionStorage) {
  if (!progress?.ratingKey) return;
  const note = { ...progress, ratingKey: String(progress.ratingKey), at: Date.now() };
  const notes = readProgressNotes(storage).filter((row) => row.ratingKey !== note.ratingKey);
  notes.push(note);
  writeProgressNotes(notes, storage);
  const cached = readExploreHubCache(storage);
  if (cached?.payload) {
    writeExploreHubCache(applyContinueWatchingProgress(cached.payload, note), storage);
  }
  if (typeof globalThis.dispatchEvent === "function" && typeof globalThis.Event === "function") {
    globalThis.dispatchEvent(new Event(CONTINUE_WATCHING_PROGRESS_EVENT));
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

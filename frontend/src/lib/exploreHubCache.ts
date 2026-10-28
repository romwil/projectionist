import type {ExploreHubPayload, JsonObject, LibraryItem, JsParam} from "../api/types";
/**
 * Session cache for Explore hub — stale-while-revalidate for snappy revisits.
 * Server also TTL-caches; this avoids a blank first paint when bouncing back
 * from chat/title detail within the same tab session.
 */

export const EXPLORE_HUB_CACHE_KEY = "projectionist.exploreHub.v1";
export const EXPLORE_HUB_CLIENT_TTL_MS = 60_000;

export function readExploreHubCache(storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null | undefined = globalThis.sessionStorage) {
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

export function writeExploreHubCache(payload: JsParam, storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null | undefined = globalThis.sessionStorage) {
  if (!storage || !payload || typeof payload !== "object") return;
  try {
    storage.setItem(EXPLORE_HUB_CACHE_KEY, JSON.stringify({ savedAt: Date.now(), payload }));
  } catch {
    // sessionStorage unavailable / quota
  }
}

export function clearExploreHubCache(storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null | undefined = globalThis.sessionStorage) {
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

function readProgressNotes(storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null | undefined) {
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

function writeProgressNotes(notes: JsParam, storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null | undefined) {
  if (!storage) return;
  try {
    storage.setItem(CONTINUE_WATCHING_PROGRESS_KEY, JSON.stringify(notes));
  } catch {
    // sessionStorage unavailable / quota
  }
}

export function continueWatchingResumeLabel(
  {
  mediaType = "",
  viewOffsetMs = 0,
  durationMs = 0,
  season = null,
  episode = null,
  episodeTitle = "",
}: JsParam = {},
) {
  const parts: unknown[] = [];
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

function continueWatchingIdentity(item: LibraryItem | null | undefined) {
  const ratingKey = String(item?.rating_key || "");
  const playKey = String(item?.play_rating_key || "");
  const mediaType = String(item?.media_type || "");
  const episodeLike = Boolean(
    mediaType === "show" ||
      mediaType === "episode" ||
      item?.continue_season != null ||
      item?.continue_episode != null ||
      (playKey && ratingKey && playKey !== ratingKey),
  );
  if (episodeLike && ratingKey) return `show:${ratingKey}`;
  return `play:${playKey || ratingKey}`;
}

export function dedupeContinueWatchingItems(items: LibraryItem[] | null | undefined) {
  const list = Array.isArray(items) ? items : [];
  const seen = new Set();
  const out: unknown[] = [];
  for (const item of list) {
    if (!item || typeof item !== "object") continue;
    const ident = continueWatchingIdentity(item);
    if (!ident || seen.has(ident)) continue;
    seen.add(ident);
    out.push(item);
  }
  return out;
}

function progressShowKey(progress: JsParam) {
  return String(progress?.showRatingKey || "").trim();
}

function titlesMatchShow(item: LibraryItem | null | undefined, progress: JsParam) {
  const wanted = String(progress?.title || "").trim().toLowerCase();
  const have = String(item?.title || "").trim().toLowerCase();
  if (!wanted || wanted !== have) return false;
  return (
    item?.media_type === "show" ||
    item?.media_type === "episode" ||
    item?.continue_season != null ||
    item?.continue_episode != null
  );
}

function progressMatchesItem(item: LibraryItem | null | undefined, progress: JsParam) {
  const ratingKey = typeof progress === "string" ? progress : String(progress?.ratingKey || "");
  const showKey = typeof progress === "string" ? "" : progressShowKey(progress);
  const play = String(item?.play_rating_key || "");
  const key = String(item?.rating_key || "");
  if (play === ratingKey || key === ratingKey) return true;
  if (showKey && (key === showKey || play === showKey)) return true;
  return false;
}

function sameShowRow(item: LibraryItem | null | undefined, progress: JsParam, cardRatingKey = "") {
  if (progressMatchesItem(item, progress)) return true;
  if (cardRatingKey && String(item?.rating_key || "") === cardRatingKey) return true;
  if (cardRatingKey && continueWatchingIdentity(item) === `show:${cardRatingKey}`) return true;
  return titlesMatchShow(item, progress);
}

function isEpisodeProgress(progress: JsParam) {
  return (
    progress?.mediaType === "episode" ||
    progress?.season != null ||
    progress?.episode != null
  );
}

function resolveShowRatingKey(items: LibraryItem[] | null | undefined, progress: JsParam) {
  const fromNote = progressShowKey(progress);
  if (fromNote) return fromNote;
  if (!isEpisodeProgress(progress)) return "";
  const ratingKey = String(progress.ratingKey || "");
  const existing = items!.find(
    (item) =>
      item?.play_rating_key === ratingKey ||
      item?.rating_key === ratingKey ||
      titlesMatchShow(item, progress),
  );
  return existing ? String(existing.rating_key || "") : "";
}

function sameProgressShow(row: JsParam, note: JsParam) {
  if (row?.ratingKey === note.ratingKey) return true;
  if (note.showRatingKey && row?.showRatingKey && row.showRatingKey === note.showRatingKey) return true;
  if (note.showRatingKey && row?.ratingKey === note.showRatingKey) return true;
  if (isEpisodeProgress(row) && isEpisodeProgress(note) && row?.title && row.title === note.title) return true;
  return false;
}

/**
 * Splice one in-app play into a hub payload's Continue Watching rail.
 * A finished play drops that episode. A new episode replaces the show's row.
 */
export function applyContinueWatchingProgress(payload: JsParam, progress: JsParam) {
  if (!payload || typeof payload !== "object" || !progress?.ratingKey) return payload;
  const ratingKey = String(progress.ratingKey);
  const offset = Math.max(0, Math.floor(Number(progress.viewOffsetMs) || 0));
  const duration = Math.max(0, Math.floor(Number(progress.durationMs) || 0));
  const finished = Boolean(progress.finished) || offset <= 0;
  const rails = payload.rails && typeof payload.rails === "object" ? payload.rails : {};
  const rail = rails.continue_watching && typeof rails.continue_watching === "object"
    ? rails.continue_watching
    : { feed: "continue-watching", items: [], total: 0, note: null };
  let items = Array.isArray(rail.items) ? rail.items.filter((item: JsParam) => item && typeof item === "object") : [];
  if (finished) {
    items = items.filter((item: JsParam) => !progressMatchesItem(item, ratingKey));
  } else {
    const mediaType = progress.mediaType === "episode" ? "episode" : progress.mediaType || "movie";
    const parentKey = mediaType === "episode" ? resolveShowRatingKey(items, progress) : "";
    const cardRatingKey = parentKey || ratingKey;
    items = items.filter((item: JsParam) => !sameShowRow(item, progress, parentKey));
    items = [
      {
        rating_key: cardRatingKey,
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
  items = dedupeContinueWatchingItems(items);
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

function railMatchesProgress(payload: JsParam, progress: JsParam) {
  const items = payload?.rails?.continue_watching?.items;
  const list = Array.isArray(items) ? items : [];
  const ratingKey = String(progress.ratingKey || "");
  const foundEpisode = list.find(
    (item) => String(item?.play_rating_key || "") === ratingKey || String(item?.rating_key || "") === ratingKey,
  );
  if (progress.finished || Number(progress.viewOffsetMs) <= 0) return !foundEpisode;
  const found = list.find((item) => progressMatchesItem(item, progress));
  if (!found) return false;
  const sameEpisode = String(found.play_rating_key || found.rating_key || "") === ratingKey;
  if (!sameEpisode) return false;
  return Number(found?.view_offset_ms) === Math.floor(Number(progress.viewOffsetMs) || 0);
}

/**
 * Replace Continue Watching from a live on-deck feed without clearing other rails.
 */
export function spliceContinueWatchingRail(payload: JsParam, liveFeed: JsParam | undefined) {
  if (!liveFeed || typeof liveFeed !== "object") return payload;
  const base = payload && typeof payload === "object" ? payload : {};
  const rails = base.rails && typeof base.rails === "object" ? base.rails : {};
  const previous =
    rails.continue_watching && typeof rails.continue_watching === "object" ? rails.continue_watching : {};
  const items = dedupeContinueWatchingItems(
    Array.isArray(liveFeed.items) ? liveFeed.items.filter((item: JsParam) => item && typeof item === "object") : [],
  );
  const note = items.length
    ? null
    : typeof liveFeed.note === "string" && liveFeed.note.trim()
      ? liveFeed.note.trim()
      : typeof previous.note === "string" && previous.note.trim()
        ? previous.note
        : "Nothing in progress — start something in Plex, or wait for watch progress to sync.";
  return {
    ...base,
    rails: {
      ...rails,
      continue_watching: {
        ...previous,
        ...liveFeed,
        feed: liveFeed.feed || "continue-watching",
        items,
        total: items.length,
        note,
        pending: false,
      },
    },
  };
}

export function dropReflectedContinueWatchingNotes(payload: JsParam, storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null | undefined = globalThis.sessionStorage) {
  const notes = readProgressNotes(storage);
  if (!notes.length) return;
  const remaining = notes.filter((note) => !railMatchesProgress(payload, note));
  writeProgressNotes(remaining, storage);
}

/**
 * Keep a play the app just recorded when a hub response is still the old snapshot.
 * Notes stay until they expire so a later stale on-deck row cannot paint over them.
 * When the payload already has that offset, the server card is left as-is.
 */
export function mergeContinueWatchingNotes(payload: JsParam, storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null | undefined = globalThis.sessionStorage) {
  const notes = readProgressNotes(storage);
  if (!payload || !notes.length) return payload;
  let next = payload;
  for (const note of notes) {
    if (railMatchesProgress(next, note)) continue;
    next = applyContinueWatchingProgress(next, note);
  }
  return next;
}

export function rememberContinueWatchingProgress(progress: JsParam, storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null | undefined = globalThis.sessionStorage) {
  if (!progress?.ratingKey) return;
  const note = {
    ...progress,
    ratingKey: String(progress.ratingKey),
    showRatingKey: String(progress.showRatingKey || "").trim(),
    at: Date.now(),
  };
  const notes = readProgressNotes(storage).filter((row) => !sameProgressShow(row, note));
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
export const EXPLORE_HUB_WARMING_POLL_MS = 1200;
export const EXPLORE_HUB_WARMING_MAX_ATTEMPTS = 30;
export const EXPLORE_HUB_WARMING_STALL_MESSAGE =
  "Explore is still warming — some shelves may be incomplete. Refresh to try again.";

export function exploreHubStillWarming(payload: JsParam) {
  return Boolean(payload?.warming);
}

export function exploreHubLoadError(err: unknown, { hasCache = false }: JsParam = {}) {
  const message = String((err as JsParam)?.message || "").trim() || "Could not load Explore.";
  if (!hasCache) return message;
  return `${message} Showing shelves from the last successful load.`;
}

/** Normalize a hub rail into the shape ExplorePage rails expect. */
export function hubRailState(hubPayload: ExploreHubPayload | null | undefined, railKey: string, { loading = false, error = "" }: JsParam = {}) {
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

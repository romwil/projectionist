/**
 * Resolve the kebab (poster action grip) "mark watched / unwatched" affordance.
 *
 * The action is offered only for titles that are in the Projectionist library and
 * carry a Plex `rating_key` — the same identity gate the center Play control
 * uses — and only when the signed-in viewer is allowed to change household
 * watched state (guests are excluded while multi-user is on, mirroring the
 * title-detail toggle). External / TMDB-only discovery cards never get it.
 *
 * The label toggles on the card's current watch progress: a watched title
 * offers "Mark as unwatched" (Plex `/:/unscrobble`), everything else offers
 * "Mark as watched" (Plex `/:/scrobble`).
 */

import { canMarkTitleWatched } from "./titleDetailExtras.js";
import { watchProgressState } from "./watchProgress.js";
import type {JsonObject, LibraryItem, JsParam} from "../api/types";

/**
 * Rating key the card actually represents for scrobble.
 * Continue Watching show cards keep the show on `rating_key` and the
 * in-progress episode on `play_rating_key`. Marking the parent show watched
 * does not complete that episode.
 * @param {Record<string, unknown> | null | undefined} item
 */
export function posterWatchRatingKey(item: LibraryItem | null | undefined) {
  return String(item?.play_rating_key || item?.rating_key || item?.plex_rating_key || "").trim();
}

/**
 * @param {Record<string, unknown> | null | undefined} item
 * @param {{ role?: string, multiUserEnabled?: boolean }} [gate]
 * @returns {{ watched: boolean, nextWatched: boolean, label: string, ratingKey: string } | null}
 *   `null` when the action must be hidden for this card/viewer.
 */
export function posterWatchAction(item: LibraryItem | null | undefined, { role, multiUserEnabled }: JsParam = {}) {
  if (!canMarkTitleWatched(item, { role, multiUserEnabled })) return null;
  const ratingKey = posterWatchRatingKey(item);
  if (!ratingKey) return null;
  const watched = watchProgressState(item) === "watched";
  return {
    watched,
    nextWatched: !watched,
    ratingKey,
    label: watched ? "Mark as unwatched" : "Mark as watched",
  };
}

/** Optimistic local patch reflecting a completed scrobble/unscrobble. */
export function watchedStatePatch(nextWatched: JsParam) {
  return nextWatched
    ? { watch_state: "watched", view_count: 1, view_offset_ms: 0, resume_label: "" }
    : { watch_state: "unwatched", view_count: 0, view_offset_ms: 0, resume_label: "" };
}

/**
 * Progress note for the Explore Continue Watching cache (1.37.40 hub merge).
 * A finished scrobble drops the in-progress row without waiting on Plex on-deck.
 */
export function continueWatchingProgressForWatched(item: LibraryItem | null | undefined, ratingKey: string, watched: boolean) {
  const episodeKey = String(item?.play_rating_key || "").trim();
  const parentKey = String(item?.rating_key || item?.plex_rating_key || "").trim();
  const isEpisode = Boolean(
    (episodeKey && parentKey && episodeKey !== parentKey)
    || item?.continue_season != null
    || item?.continue_episode != null,
  );
  return {
    ratingKey: String(ratingKey),
    showRatingKey: isEpisode ? parentKey : "",
    viewOffsetMs: 0,
    durationMs: Number(item?.duration_ms) || 0,
    finished: Boolean(watched),
    title: item?.title || "",
    mediaType: isEpisode ? "episode" : (item?.media_type || "movie"),
    season: item?.continue_season ?? null,
    episode: item?.continue_episode ?? null,
    episodeTitle: item?.continue_episode_title || "",
    posterUrl: item?.poster_url || "",
    year: item?.year ?? null,
  };
}

/**
 * Mark the card's rating key watched/unwatched, then update local Continue Watching.
 * @param {Record<string, unknown>} item
 * @param {{ watched: boolean, setWatched: (key: string, watched: boolean) => Promise<unknown>, rememberProgress?: (note: object) => void }} deps
 */
export async function commitPosterWatched(item: LibraryItem | null | undefined, { watched, setWatched, rememberProgress }: JsParam) {
  const ratingKey = posterWatchRatingKey(item);
  if (!ratingKey) {
    throw new Error("This title has no rating key to mark watched.");
  }
  const result = await setWatched(ratingKey, watched);
  const patch = watchedStatePatch(watched);
  if (result && typeof result.view_count === "number") patch.view_count = result.view_count;
  rememberProgress?.(continueWatchingProgressForWatched(item, ratingKey, watched));
  return { ratingKey, result, patch };
}

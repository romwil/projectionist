/**
 * Resolve the kebab (poster action grip) "mark watched / unwatched" affordance.
 *
 * The action is offered only for titles that are in the CuratorX library and
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

/**
 * @param {Record<string, unknown> | null | undefined} item
 * @param {{ role?: string, multiUserEnabled?: boolean }} [gate]
 * @returns {{ watched: boolean, nextWatched: boolean, label: string } | null}
 *   `null` when the action must be hidden for this card/viewer.
 */
export function posterWatchAction(item, { role, multiUserEnabled } = {}) {
  if (!canMarkTitleWatched(item, { role, multiUserEnabled })) return null;
  const watched = watchProgressState(item) === "watched";
  return {
    watched,
    nextWatched: !watched,
    label: watched ? "Mark as unwatched" : "Mark as watched",
  };
}

/** Optimistic local patch reflecting a completed scrobble/unscrobble. */
export function watchedStatePatch(nextWatched) {
  return nextWatched
    ? { watch_state: "watched", view_count: 1 }
    : { watch_state: "unwatched", view_count: 0, view_offset_ms: 0 };
}

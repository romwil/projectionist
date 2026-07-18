/**
 * Shared watch-progress classification for poster badges.
 * Mirrors curatorx.library.watch_progress.watch_progress_state.
 *
 * Movies:
 * - watched: view_count > 0
 * - partial: view_offset_ms > 0 with view_count === 0 (needs Plex sync)
 * - unwatched: otherwise
 *
 * Shows:
 * - watched: total_episode_count > 0 && unwatched_episode_count === 0
 * - partial: 0 < unwatched < total
 * - fallback when episode counts missing: view_count > 0 → watched
 */

function asNonNegInt(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return 0;
  return Math.floor(n);
}

/**
 * @param {Record<string, unknown> | null | undefined} item
 * @returns {"unwatched" | "partial" | "watched"}
 */
export function watchProgressState(item) {
  if (!item || typeof item !== "object") return "unwatched";

  // Privacy/member sanitization may replace raw counters with watch_state.
  const explicit = String(item.watch_state || "")
    .trim()
    .toLowerCase();
  if (explicit === "watched") return "watched";
  if (explicit === "partial" || explicit === "in_progress") return "partial";
  if (explicit === "unwatched") return "unwatched";

  const media = String(item.media_type || "")
    .trim()
    .toLowerCase();
  const viewCount = asNonNegInt(item.view_count);
  const viewOffsetMs = asNonNegInt(item.view_offset_ms);
  const total = asNonNegInt(item.total_episode_count);
  const unwatched = asNonNegInt(item.unwatched_episode_count);

  // Episode totals imply show semantics even when media_type is omitted.
  const isShow = media === "show" || media === "tv" || media === "series" || total > 0;
  if (isShow) {
    if (total > 0) {
      if (unwatched <= 0) return "watched";
      if (unwatched < total) return "partial";
      return "unwatched";
    }
    return viewCount > 0 ? "watched" : "unwatched";
  }

  if (viewCount > 0) return "watched";
  if (viewOffsetMs > 0) return "partial";
  return "unwatched";
}

/** Aria / title copy for a watch-progress state. */
export function watchProgressLabel(state) {
  if (state === "watched") return "Watched";
  if (state === "partial") return "In progress";
  return "";
}

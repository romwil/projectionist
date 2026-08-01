/** Pure helpers for TV show seasons / episodes on title detail. */

export function formatEpisodeCode(seasonNumber, episodeNumber) {
  const season = Number.isFinite(Number(seasonNumber)) ? Number(seasonNumber) : 0;
  const episode = Number.isFinite(Number(episodeNumber)) ? Number(episodeNumber) : 0;
  return `S${String(season).padStart(2, "0")}E${String(episode).padStart(2, "0")}`;
}

export function formatSeasonLabel(seasonNumber) {
  if (seasonNumber == null || seasonNumber === "") return "Specials";
  const n = Number(seasonNumber);
  if (!Number.isFinite(n)) return "Season";
  if (n === 0) return "Specials";
  return `Season ${n}`;
}

export function formatShowBytes(bytes) {
  const value = Number(bytes) || 0;
  if (value <= 0) return "";
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(0)} MB`;
  return `${(value / 1024 ** 3).toFixed(1)} GB`;
}

export function normalizeShowSeasonsPayload(payload) {
  const seasons = Array.isArray(payload?.seasons)
    ? payload.seasons.map((season) => {
        const episodes = Array.isArray(season?.episodes)
          ? season.episodes.map((ep) => ({
              id: ep?.id ?? null,
              rating_key: String(ep?.rating_key || "").trim() || null,
              season_number:
                ep?.season_number == null || ep?.season_number === ""
                  ? null
                  : Number(ep.season_number),
              episode_number:
                ep?.episode_number == null || ep?.episode_number === ""
                  ? null
                  : Number(ep.episode_number),
              title: String(ep?.title || "").trim() || "Untitled",
              runtime_minutes: Number(ep?.runtime_minutes) || null,
              view_count: Number(ep?.view_count) || 0,
              unwatched: Boolean(ep?.unwatched ?? !(Number(ep?.view_count) > 0)),
              file_size: Number(ep?.file_size) || 0,
              aired_at: String(ep?.aired_at || "") || null,
            }))
          : [];
        return {
          season_number:
            season?.season_number == null || season?.season_number === ""
              ? null
              : Number(season.season_number),
          episode_count: Number(season?.episode_count) || episodes.length,
          watched_count: Number(season?.watched_count) || 0,
          file_size_bytes: Number(season?.file_size_bytes) || 0,
          episodes,
        };
      })
    : [];
  return {
    show_id: payload?.show_id ?? null,
    show_title: String(payload?.show_title || "").trim(),
    rating_key: String(payload?.rating_key || "").trim() || null,
    tmdb_id: payload?.tmdb_id ?? null,
    tvdb_id: payload?.tvdb_id ?? null,
    total_seasons: Number(payload?.total_seasons) || seasons.length,
    total_episodes: Number(payload?.total_episodes) || 0,
    file_size_bytes: Number(payload?.file_size_bytes) || 0,
    truncated: Boolean(payload?.truncated),
    seasons,
  };
}

export function showSeasonsSummaryLine(data) {
  if (!data) return "";
  const seasons = Number(data.total_seasons) || 0;
  const episodes = Number(data.total_episodes) || 0;
  const size = formatShowBytes(data.file_size_bytes);
  const parts = [
    `${seasons} season${seasons === 1 ? "" : "s"}`,
    `${episodes} episode${episodes === 1 ? "" : "s"}`,
  ];
  if (size) parts.push(size);
  return parts.join(" · ");
}

/**
 * Live guide / OSD helpers for episode + movie detail labeling and dig-in.
 *
 * Soft-fail: never invent episode titles — fall back to the show/movie name.
 */

/**
 * @param {unknown} value
 * @returns {string}
 */
function trimText(value) {
  return String(value ?? "").trim();
}

/**
 * @param {object|null|undefined} program
 * @returns {string}
 */
export function programTitle(program) {
  return trimText(program?.title);
}

/**
 * Real episode title only — empty when Tunarr/guide did not provide one.
 * @param {object|null|undefined} program
 * @returns {string}
 */
export function programEpisodeTitle(program) {
  const title = programTitle(program);
  const fromFields =
    trimText(program?.episode_title) || trimText(program?.episodeTitle);
  // Guide cells may put the episode title on `episode`; API rows use a number there.
  const episodeField = program?.episode;
  const fromEpisodeField =
    typeof episodeField === "string" && !/^\d+$/.test(episodeField.trim())
      ? trimText(episodeField)
      : "";
  const raw = fromFields || fromEpisodeField;
  // Guard: some normalizers stash the show name in episode when missing.
  if (!raw || (title && raw.toLowerCase() === title.toLowerCase())) return "";
  // Reject SxxExx-only tokens that are not titles.
  if (/^s\d+e\d+$/i.test(raw)) return "";
  return raw;
}

/**
 * @param {unknown} value
 * @returns {number|null}
 */
function asInt(value) {
  if (value == null || value === "") return null;
  // Guide UI cells may put the episode *title* on `episode` — reject non-integers.
  if (typeof value === "string" && !/^\d+$/.test(value.trim())) return null;
  const number = Number(value);
  return Number.isFinite(number) ? Math.trunc(number) : null;
}

/**
 * @param {object|null|undefined} program
 * @returns {{ season: number|null, episode: number|null }}
 */
export function programSeasonEpisode(program) {
  const season = asInt(program?.season ?? program?.seasonNumber);
  const episode =
    asInt(program?.episode_number) ??
    asInt(program?.episodeNumber) ??
    asInt(program?.episode);
  return { season, episode };
}

/**
 * Compact ``S2E4`` (or ``E4``) when numbers exist.
 * @param {object|null|undefined} program
 * @returns {string}
 */
export function formatSeasonEpisodeCode(program) {
  const { season, episode } = programSeasonEpisode(program);
  if (season != null && episode != null) return `S${season}E${episode}`;
  if (episode != null) return `E${episode}`;
  return "";
}

/**
 * Secondary line for guide pods / OSD — episode title, optionally with SxxExx.
 * Empty when metadata is missing (soft-fail to show name only).
 * @param {object|null|undefined} program
 * @returns {string}
 */
export function formatProgramEpisodeLabel(program) {
  const epTitle = programEpisodeTitle(program);
  const code = formatSeasonEpisodeCode(program);
  if (epTitle && code) return `${code} · ${epTitle}`;
  if (epTitle) return epTitle;
  if (code) return code;
  return "";
}

/**
 * Primary + episode for “Up next” / Next rows.
 * Movies: ``Title (year)`` when year is known.
 * @param {object|null|undefined} program
 * @returns {string}
 */
export function formatProgramDisplayTitle(program) {
  const title = programTitle(program);
  if (!title) return "";
  const mediaType = trimText(program?.media_type || program?.mediaType).toLowerCase();
  const epLabel = formatProgramEpisodeLabel(program);
  if (epLabel && mediaType !== "movie") {
    return `${title} — ${epLabel}`;
  }
  const year = Number(program?.year);
  if (Number.isFinite(year) && year > 1000) {
    return `${title} (${year})`;
  }
  return title;
}

/**
 * Dig-in card for TitleDetailLink / overlay. Soft-null when unlinkable.
 * Episodes dig into the **show** (library indexes shows, not episode keys).
 * @param {object|null|undefined} program
 * @returns {Record<string, unknown>|null}
 */
export function programDigInItem(program) {
  if (!program || typeof program !== "object") return null;
  if (program.is_flex || program.isFlex) return null;
  const title = programTitle(program);
  const mediaTypeRaw = trimText(program.media_type || program.mediaType).toLowerCase();
  const epTitle = programEpisodeTitle(program);
  const mediaType =
    mediaTypeRaw === "show" || mediaTypeRaw === "episode" || epTitle
      ? "show"
      : mediaTypeRaw === "movie"
        ? "movie"
        : epTitle
          ? "show"
          : "movie";
  const showKey = trimText(
    program.show_plex_rating_key || program.showPlexRatingKey || "",
  );
  const contentKey = trimText(
    program.plex_rating_key || program.plexRatingKey || program.rating_key || "",
  );
  const ratingKey = mediaType === "show" ? showKey || contentKey : contentKey || showKey;
  if (!ratingKey) return null;
  const year = Number(program.year);
  return {
    title,
    media_type: mediaType,
    rating_key: ratingKey,
    plex_rating_key: ratingKey,
    in_library: true,
    year: Number.isFinite(year) && year > 1000 ? year : undefined,
  };
}

/**
 * Hover popup model for guide pods / Up next.
 * @param {object|null|undefined} program
 * @param {{ kind?: "now"|"next"|"guide" }} [options]
 */
export function buildProgramHoverModel(program, { kind = "guide" } = {}) {
  if (!program || typeof program !== "object") return null;
  const title = programTitle(program);
  if (!title) return null;
  const episodeLabel = formatProgramEpisodeLabel(program);
  const overview = trimText(program.overview || program.summary || "");
  const rating = trimText(program.content_rating || program.rating || "");
  const year = Number(program.year);
  const yearLabel = Number.isFinite(year) && year > 1000 ? String(year) : "";
  const mediaType = trimText(program.media_type || program.mediaType).toLowerCase();
  const isMovie = mediaType === "movie" || (!episodeLabel && yearLabel && mediaType !== "show");
  const digInItem = programDigInItem(program);
  const eyebrow =
    kind === "next" ? "Up next" : kind === "now" ? "On now" : isMovie ? "Movie" : "Episode";
  return {
    eyebrow,
    title,
    subtitle: episodeLabel || (yearLabel && isMovie ? yearLabel : ""),
    year: yearLabel,
    overview,
    rating,
    isFlex: Boolean(program.is_flex || program.isFlex),
    isMovie,
    digInItem,
    displayTitle: formatProgramDisplayTitle(program),
  };
}

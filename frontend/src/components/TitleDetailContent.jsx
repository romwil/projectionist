import { Link } from "react-router-dom";
import {
  isAddableToRadarr,
  isAddableToSonarr,
  isRequestableInSeerr,
  itemNeedsAddGuidance,
  resolveAddCapability,
} from "../lib/addActions.js";
import {
  exploreCastPath,
  exploreDirectorsPath,
  exploreGenrePath,
  personPath,
  tagPath,
} from "../lib/browseLinks.js";
import { canOwnerDeleteLibraryTitle } from "../lib/bulkLibraryDelete.js";
import { displayRecommendationReason } from "../lib/recommendationReason.js";
import {
  canMarkTitleWatched,
  formatTitleReleaseBadge,
  formatTvProgress,
  isTitleWatched,
  reviewsCtaForDetail,
  watchedCtaLabel,
} from "../lib/titleDetailExtras.js";
import {
  countryBrowsePath,
  decadeBrowsePath,
  decadeLabel,
  languageBrowseMeta,
} from "../lib/titleDetailMeta.js";
import { canWatchOnPlex, plexWatchUrl } from "../lib/titleLinks.js";

const META_LINK_CLASS = "title-meta-link";
const META_STATIC_CLASS = "title-meta-static";

function creditLink(credit) {
  const path = personPath(credit?.tmdb_person_id);
  if (path) return path;
  const name = String(credit?.name || "").trim();
  if (!name) return null;
  if (String(credit?.job || "") === "Director" || String(credit?.department || "") === "Directing") {
    return exploreDirectorsPath(name);
  }
  return exploreCastPath(name);
}

function CreditLink({ credit, children, testId }) {
  const to = creditLink(credit);
  if (!to) {
    return <span className={META_STATIC_CLASS}>{children}</span>;
  }
  return (
    <Link to={to} className={META_LINK_CLASS} data-testid={testId}>
      {children}
    </Link>
  );
}

function MetaLink({ to, children, testId }) {
  if (!to) {
    return <span className={META_STATIC_CLASS}>{children}</span>;
  }
  return (
    <Link to={to} className={META_LINK_CLASS} data-testid={testId}>
      {children}
    </Link>
  );
}

function formatFileSize(bytes) {
  if (!bytes || bytes <= 0) return null;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(0)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

function MetaTile({ label, value }) {
  if (!value) return null;
  return (
    <div className="title-meta-tile">
      <span className="title-meta-tile-label">{label}</span>
      <span className={META_STATIC_CLASS}>{value}</span>
    </div>
  );
}

/**
 * Shared title detail presentation for the full page and slide-over drawer.
 * Action handlers and modal state live in the parent surface.
 */
export default function TitleDetailContent({
  detail,
  variant = "full",
  fullPageHref = null,
  multiUserEnabled = false,
  userRole = "owner",
  requestPath = "arr",
  addStatus = null,
  addMessage = "",
  watchStatus = null,
  watchMessage = "",
  deleting = false,
  onRequestAdd,
  onToggleWatched,
  onOpenTrailer,
  onOpenReview,
  onOpenRecommend,
  onOpenDelete,
  titleId,
}) {
  if (!detail) return null;

  const compact = variant === "compact";
  const trailerKey = String(detail.trailer_youtube_key || "").trim();
  const plexHref =
    String(detail.plex_watch_url || "").trim() ||
    (canWatchOnPlex(detail) ? plexWatchUrl(detail.rating_key, detail.plex_machine_id || "") : "");
  const whyReason = displayRecommendationReason(detail.recommendation_reason);
  const showWhy = Boolean(whyReason);
  const purgeNote = String(detail.purge_reason || "").trim();
  const runtimeLabel = detail.runtime_minutes ? `${detail.runtime_minutes} mins` : null;
  const sizeLabel = formatFileSize(detail.file_size_bytes || detail.file_size);
  const tvProgress = detail.media_type === "show" ? formatTvProgress(detail) : null;
  const reviewsCta = reviewsCtaForDetail(detail);
  const releaseDateLabel = formatTitleReleaseBadge({
    releaseDate: detail.release_date,
    firstAirDate: detail.first_air_date,
    year: detail.year,
    mediaType: detail.media_type,
  });

  const credits = (() => {
    const raw = Array.isArray(detail.credits) ? detail.credits : [];
    if (raw.length) return raw;
    const fallback = [];
    for (const name of detail.directors || []) {
      if (!name) continue;
      fallback.push({ name, job: "Director", department: "Directing" });
    }
    for (const name of detail.cast || []) {
      if (!name) continue;
      fallback.push({ name, job: "Actor", department: "Acting" });
    }
    return fallback;
  })();

  const directorCredits = credits.filter(
    (c) => String(c.job || "") === "Director" || String(c.department || "") === "Directing",
  );
  const castCredits = credits.filter(
    (c) => String(c.job || "") !== "Director" && String(c.department || "") !== "Directing",
  );
  const directorCredit = directorCredits[0] || null;
  const genreChips = Array.isArray(detail.genres) ? detail.genres.slice(0, compact ? 3 : 2) : [];
  const addCapability = resolveAddCapability({
    role: userRole,
    requestPath,
    multiUserEnabled,
  });
  const canRequestSeerr = addCapability.canRequest && isRequestableInSeerr(detail);
  const canAddRadarr = addCapability.canAdd && isAddableToRadarr(detail);
  const canAddSonarr = addCapability.canAdd && isAddableToSonarr(detail);
  const canAddOrRequest = canRequestSeerr || canAddRadarr || canAddSonarr;
  const showAskOwner = addCapability.showGuidedCopy && itemNeedsAddGuidance(detail);
  const canDeleteLibrary = canOwnerDeleteLibraryTitle(detail, {
    role: userRole,
    multiUserEnabled,
  });
  const canToggleWatched = canMarkTitleWatched(detail, {
    role: userRole,
    multiUserEnabled,
  });
  const addCtaLabel = canRequestSeerr
    ? "Request in Seerr"
    : canAddSonarr
      ? "Add to Sonarr"
      : "Add to Radarr";
  const decadeValue = decadeLabel(detail.year);
  const decadePath = decadeBrowsePath(detail.year);
  const languageMeta = languageBrowseMeta(detail.original_language);
  const countryValues = Array.isArray(detail.countries) ? detail.countries.slice(0, compact ? 2 : 4) : [];
  const contentRating = String(detail.content_rating || "").trim();
  const castLimit = compact ? 4 : 6;
  const tagLimit = compact ? 5 : 8;

  const headlineId = titleId || "title-detail-headline";

  return (
    <div
      className={`title-detail-content${compact ? " title-detail-content--compact" : ""}`}
      data-testid={compact ? "title-detail-drawer-content" : "title-detail-content"}
    >
      {compact && detail.poster_url ? (
        <div className="title-detail-drawer-poster" aria-hidden="true">
          <img src={detail.poster_url} alt="" loading="lazy" />
        </div>
      ) : null}

      <section
        className="title-detail-hero"
        style={detail.backdrop_url ? { "--title-backdrop": `url(${detail.backdrop_url})` } : undefined}
        data-testid="title-detail-hero"
      >
        <div className="title-detail-hero-scrim" aria-hidden="true" />
        <div className="title-detail-hero-inner">
          <div className="title-detail-chips">
            {releaseDateLabel ? (
              <span className="title-chip" data-testid="title-release-chip">
                {releaseDateLabel}
              </span>
            ) : null}
            {runtimeLabel ? (
              <span className="title-chip title-chip-accent">
                <span className="material-symbols-outlined" aria-hidden="true">
                  schedule
                </span>
                {runtimeLabel}
              </span>
            ) : null}
            {tvProgress ? (
              <span className="title-chip title-chip-accent" data-testid="title-tv-progress-chip">
                {tvProgress.label}
              </span>
            ) : null}
            {detail.in_library ? <span className="title-chip title-chip-success">In library</span> : null}
            {detail.rating ? (
              <span className="title-chip title-chip-accent" data-testid="title-tmdb-rating-chip">
                TMDB ★ {Number(detail.rating).toFixed(1)}
              </span>
            ) : null}
          </div>
          <div className="title-detail-headline-row">
            <h1 className="title-detail-headline" id={headlineId}>
              {detail.title}
            </h1>
            {contentRating ? (
              <span className="title-content-rating-chip" data-testid="title-content-rating-chip">
                {contentRating}
              </span>
            ) : null}
          </div>
          <div className="title-detail-cta-row">
            {plexHref ? (
              <a
                href={plexHref}
                className="title-cta title-cta-primary"
                data-testid="watch-on-plex-button"
                target="_blank"
                rel="noopener noreferrer"
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  play_circle
                </span>
                Watch on Plex
              </a>
            ) : null}
            {trailerKey ? (
              <button
                type="button"
                className="title-cta title-cta-ghost"
                data-testid="watch-trailer-button"
                onClick={onOpenTrailer}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  play_arrow
                </span>
                Trailer
              </button>
            ) : null}
            {reviewsCta?.kind === "rate" ? (
              <button
                type="button"
                className="title-cta title-cta-ghost"
                data-testid="title-reviews-cta"
                onClick={onOpenReview}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  rate_review
                </span>
                {reviewsCta.label}
              </button>
            ) : null}
            {canToggleWatched ? (
              <button
                type="button"
                className="title-cta title-cta-ghost"
                data-testid="title-watched-cta"
                disabled={watchStatus === "loading"}
                onClick={onToggleWatched}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  {isTitleWatched(detail) ? "visibility_off" : "visibility"}
                </span>
                {watchStatus === "loading" ? "Updating…" : watchedCtaLabel(detail)}
              </button>
            ) : null}
            {canAddOrRequest ? (
              <button
                type="button"
                className={`title-cta ${plexHref ? "title-cta-ghost" : "title-cta-primary"}`}
                data-testid="title-detail-add-button"
                disabled={addStatus === "loading" || addStatus === "success"}
                onClick={onRequestAdd}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  add_circle
                </span>
                {addStatus === "loading"
                  ? "Adding…"
                  : addStatus === "success"
                    ? "Added"
                    : addCtaLabel}
              </button>
            ) : null}
            {showAskOwner ? (
              <span
                className="title-cta title-cta-ghost title-cta-disabled"
                data-testid="title-detail-ask-owner"
                title="Guests cannot request or add media"
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  lock
                </span>
                {addCapability.guidedCopy}
              </span>
            ) : null}
            {multiUserEnabled ? (
              <button
                type="button"
                className="title-cta title-cta-icon"
                data-testid="recommend-title-button"
                aria-label="Recommend to…"
                onClick={onOpenRecommend}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  person_add
                </span>
              </button>
            ) : null}
            {canDeleteLibrary ? (
              <button
                type="button"
                className="title-cta title-cta-danger"
                data-testid="title-detail-delete-button"
                disabled={deleting}
                onClick={onOpenDelete}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  delete
                </span>
                Delete
              </button>
            ) : null}
          </div>
          {addMessage ? (
            <p
              className={`title-detail-add-feedback ${addStatus === "error" ? "is-error" : ""}`}
              data-testid="title-detail-add-feedback"
            >
              {addMessage}
            </p>
          ) : null}
          {watchMessage ? (
            <p
              className={`title-detail-add-feedback ${watchStatus === "error" ? "is-error" : ""}`}
              data-testid="title-watched-feedback"
            >
              {watchMessage}
            </p>
          ) : null}
        </div>
      </section>

      <section className="title-detail-grid">
        <div className="title-detail-main">
          {detail.overview ? (
            <div className="title-detail-section">
              <h2 className="title-detail-section-label">Synopsis</h2>
              <p className="title-detail-synopsis">{detail.overview}</p>
            </div>
          ) : null}

          {showWhy ? (
            <div className="title-why-card" data-testid="title-why-card">
              <h2 className="title-why-heading">Why this?</h2>
              <p className="title-why-body">{whyReason}</p>
              <p className="title-why-badge">
                <span className="material-symbols-outlined" aria-hidden="true">
                  auto_awesome
                </span>
                Curator note
              </p>
            </div>
          ) : null}

          {purgeNote ? (
            <aside className="title-purge-callout" data-testid="title-purge-callout">
              <span className="material-symbols-outlined" aria-hidden="true">
                warning
              </span>
              <div>
                <h3>Purge notes</h3>
                <p>{purgeNote}</p>
              </div>
            </aside>
          ) : null}
        </div>

        <aside className="title-detail-side">
          <div className="title-meta-grid">
            <MetaTile label="Released" value={releaseDateLabel} />
            {decadeValue ? (
              <div className="title-meta-tile">
                <span className="title-meta-tile-label">Decade</span>
                <MetaLink to={decadePath} testId="title-decade-link">
                  {decadeValue}
                </MetaLink>
              </div>
            ) : null}
            {!compact ? <MetaTile label="Collection" value={detail.collection_name || null} /> : null}
            {tvProgress ? <MetaTile label="Progress" value={tvProgress.label} /> : null}
            {reviewsCta?.kind === "rated" ? (
              <MetaTile
                label="Your rating"
                value={reviewsCta.label.replace(/^Your rating:\s*/, "")}
              />
            ) : null}
            {languageMeta ? (
              <div className="title-meta-tile">
                <span className="title-meta-tile-label">Language</span>
                <MetaLink to={languageMeta.path} testId="title-language-link">
                  {languageMeta.label}
                </MetaLink>
              </div>
            ) : null}
            {countryValues.length ? (
              <div className="title-meta-tile">
                <span className="title-meta-tile-label">Countries</span>
                <span className="title-meta-facet-list">
                  {countryValues.map((country, index) => (
                    <span key={country}>
                      {index > 0 ? " · " : null}
                      <MetaLink to={countryBrowsePath(country)} testId="title-country-link">
                        {country}
                      </MetaLink>
                    </span>
                  ))}
                </span>
              </div>
            ) : null}
            {!compact ? <MetaTile label="Status" value={detail.status || null} /> : null}
            {directorCredit ? (
              <div className="title-meta-tile">
                <span className="title-meta-tile-label">Director</span>
                <CreditLink credit={directorCredit} testId="title-director-link">
                  {directorCredit.name}
                </CreditLink>
              </div>
            ) : null}
            {genreChips.length ? (
              <div className="title-meta-tile">
                <span className="title-meta-tile-label">Genre</span>
                <span className="title-meta-facet-list">
                  {genreChips.map((genre, index) => (
                    <span key={genre}>
                      {index > 0 ? " · " : null}
                      <MetaLink to={exploreGenrePath(genre)} testId="title-genre-link">
                        {genre}
                      </MetaLink>
                    </span>
                  ))}
                </span>
              </div>
            ) : null}
            <MetaTile label="Size" value={sizeLabel} />
            <MetaTile
              label="Views"
              value={detail.view_count > 0 ? String(detail.view_count) : null}
            />
          </div>

          {!compact && detail.keywords?.length ? (
            <div className="title-detail-section">
              <h2 className="title-detail-section-label">Tags</h2>
              <div className="title-tag-list">
                {detail.keywords.slice(0, tagLimit).map((tag) => {
                  const to = tagPath(tag);
                  return to ? (
                    <Link
                      key={tag}
                      to={to}
                      className="title-tag title-meta-link title-tag-link"
                      data-testid="title-tag-link"
                    >
                      {tag}
                    </Link>
                  ) : (
                    <span key={tag} className="title-tag">
                      {tag}
                    </span>
                  );
                })}
              </div>
            </div>
          ) : null}

          {castCredits.length ? (
            <div className="title-detail-section">
              <h2 className="title-detail-section-label">Cast</h2>
              <ul className="title-cast-list">
                {castCredits.slice(0, castLimit).map((credit) => (
                  <li key={`${credit.tmdb_person_id || credit.name}-${credit.character || ""}`}>
                    <CreditLink credit={credit} testId="title-cast-link">
                      {credit.name}
                    </CreditLink>
                    {credit.character ? (
                      <span className="title-cast-role">{credit.character}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </aside>
      </section>

      {compact && fullPageHref ? (
        <p className="title-detail-drawer-full-link">
          <Link to={fullPageHref} className="title-meta-link" data-testid="title-detail-open-full">
            Open full page
          </Link>
        </p>
      ) : null}
    </div>
  );
}

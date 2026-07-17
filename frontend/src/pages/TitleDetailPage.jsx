import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import BackLink from "../components/BackLink";
import {
  api,
  confirmAction,
  formatApiError,
  getFeatures,
  proposeAction,
  queryLibrary,
} from "../api/client";
import RecommendModal from "../components/RecommendModal";
import AppShell from "../layouts/AppShell";
import {
  alreadyInArrMessage,
  buildProposeActionBody,
  isAddableToRadarr,
  isAddableToSonarr,
  isAlreadyInArr,
  isRequestableInSeerr,
  itemNeedsAddGuidance,
  normalizeUserRole,
  requestPathFromFeatures,
  resolveAddCapability,
  serviceLabelForTarget,
} from "../lib/addActions.js";
import { rateFlowHref } from "../lib/backNav.js";
import {
  ROUTES,
  exploreCastPath,
  exploreDirectorsPath,
  exploreGenrePath,
  personPath,
  tagPath,
} from "../lib/browseLinks.js";
import { displayRecommendationReason } from "../lib/recommendationReason.js";
import {
  filterCollectionPeers,
  formatTvProgress,
  reviewsCtaForDetail,
} from "../lib/titleDetailExtras.js";
import { canWatchOnPlex, plexWatchUrl, titleDetailPath } from "../lib/titleLinks.js";

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

function CreditLink({ credit, children, className, testId }) {
  const to = creditLink(credit);
  if (!to) {
    return <span className={className}>{children}</span>;
  }
  return (
    <Link to={to} className={className} data-testid={testId}>
      {children}
    </Link>
  );
}

function decadeLabel(year) {
  if (!year || year < 1000) return null;
  return `${Math.floor(year / 10) * 10}s`;
}

function formatFileSize(bytes) {
  if (!bytes || bytes <= 0) return null;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(0)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

function formatReleaseDate(value) {
  const raw = String(value || "").trim();
  if (!raw) return null;
  // Prefer full YYYY-MM-DD when available; fall back to year-only.
  const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (match) {
    const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleDateString(undefined, {
        year: "numeric",
        month: "long",
        day: "numeric",
        timeZone: "UTC",
      });
    }
  }
  if (/^\d{4}$/.test(raw)) return raw;
  return raw.slice(0, 10);
}

function MetaTile({ label, value }) {
  if (!value) return null;
  return (
    <div className="title-meta-tile">
      <span className="title-meta-tile-label">{label}</span>
      <span className="title-meta-tile-value">{value}</span>
    </div>
  );
}

export default function TitleDetailPage() {
  const { mediaType, itemId } = useParams();
  const [searchParams] = useSearchParams();
  const idType = searchParams.get("id_type") || "tmdb";
  const [detail, setDetail] = useState(null);
  const [neighbors, setNeighbors] = useState(null);
  const [neighborMode, setNeighborMode] = useState("similar");
  const [error, setError] = useState("");
  const [trailerOpen, setTrailerOpen] = useState(false);
  const [recommendOpen, setRecommendOpen] = useState(false);
  const [multiUserEnabled, setMultiUserEnabled] = useState(false);
  const [userRole, setUserRole] = useState("owner");
  const [requestPath, setRequestPath] = useState("arr");
  const [addStatus, setAddStatus] = useState(null); // loading | success | error
  const [addMessage, setAddMessage] = useState("");
  const [collectionPeers, setCollectionPeers] = useState([]);
  const carouselRef = useRef(null);

  useEffect(() => {
    setDetail(null);
    setNeighbors(null);
    setNeighborMode("similar");
    setError("");
    setTrailerOpen(false);
    setRecommendOpen(false);
    setAddStatus(null);
    setAddMessage("");

    const controller = new AbortController();
    const enrichController = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 12_000);

    const params = new URLSearchParams();
    if (idType && idType !== "tmdb") params.set("id_type", idType);
    // First paint from local library data; TMDB trailer/rating fill in afterwards.
    params.set("enrich", "0");
    const query = params.toString() ? `?${params.toString()}` : "";

    api(`/title/${mediaType}/${itemId}${query}`, { signal: controller.signal })
      .then((data) => {
        setDetail(data);
        const enrichParams = new URLSearchParams(params);
        enrichParams.set("enrich", "1");
        // Progressive enrichment is best-effort; never replace a successful first paint with an error.
        api(`/title/${mediaType}/${itemId}?${enrichParams.toString()}`, {
          signal: enrichController.signal,
        })
          .then((enriched) => {
            if (enriched) setDetail(enriched);
          })
          .catch(() => {});
      })
      .catch((err) => {
        if (err?.name === "AbortError") {
          setError("Timed out loading this title. Try again.");
          return;
        }
        setError(err.message || "Failed to load title");
      })
      .finally(() => window.clearTimeout(timeoutId));

    return () => {
      window.clearTimeout(timeoutId);
      controller.abort();
      enrichController.abort();
    };
  }, [mediaType, itemId, idType]);

  useEffect(() => {
    setNeighbors(null);
    const neighborQuery = new URLSearchParams({
      limit: "12",
      mode: neighborMode === "surprising" ? "surprising" : "similar",
    });
    if (idType && idType !== "tmdb") neighborQuery.set("id_type", idType);
    api(`/title/${mediaType}/${itemId}/neighbors?${neighborQuery}`)
      .then((data) => setNeighbors(Array.isArray(data?.items) ? data.items : []))
      .catch(() => setNeighbors([]));
  }, [mediaType, itemId, idType, neighborMode]);

  useEffect(() => {
    getFeatures()
      .then((data) => {
        const enabled = Boolean(data?.features?.multi_user_enabled);
        setMultiUserEnabled(enabled);
        setRequestPath(requestPathFromFeatures(data));
        setUserRole(normalizeUserRole(data?.user?.role, { multiUserEnabled: enabled }));
      })
      .catch(() => {
        setMultiUserEnabled(false);
        setUserRole("owner");
        setRequestPath("arr");
      });
  }, []);

  useEffect(() => {
    const name = String(detail?.collection_name || "").trim();
    if (!name) {
      setCollectionPeers([]);
      return undefined;
    }
    let cancelled = false;
    queryLibrary({ collection_name: name, limit: 16, sort: "year" })
      .then((data) => {
        if (cancelled) return;
        setCollectionPeers(filterCollectionPeers(data?.items || [], detail, { limit: 12 }));
      })
      .catch(() => {
        if (!cancelled) setCollectionPeers([]);
      });
    return () => {
      cancelled = true;
    };
  }, [detail]);

  async function handleRequestAdd() {
    const capability = resolveAddCapability({
      role: userRole,
      requestPath,
      multiUserEnabled,
    });
    if (!capability.canAdd && !capability.canRequest) return;
    if (!detail || addStatus === "loading" || addStatus === "success") return;
    const target =
      requestPath === "seerr"
        ? "seerr"
        : detail.media_type === "show"
          ? "sonarr"
          : "radarr";
    const label = detail.title || "this title";
    const service = serviceLabelForTarget(target);
    setAddStatus("loading");
    setAddMessage("");
    try {
      const proposal = await proposeAction(buildProposeActionBody(detail, target));
      if (isAlreadyInArr(proposal)) {
        setAddStatus("success");
        setAddMessage(alreadyInArrMessage(proposal, { label, service }));
        return;
      }
      const confirm = await confirmAction(proposal.confirmation_token);
      if (isAlreadyInArr(confirm)) {
        setAddStatus("success");
        setAddMessage(alreadyInArrMessage(confirm, { label, service }));
        return;
      }
      setAddStatus("success");
      setAddMessage(
        target === "seerr" ? `Requested "${label}" in Seerr.` : `Added "${label}" to ${service}.`,
      );
    } catch (err) {
      setAddStatus("error");
      setAddMessage(formatApiError(err));
    }
  }

  useEffect(() => {
    if (!trailerOpen) return undefined;
    function onKey(event) {
      if (event.key === "Escape") setTrailerOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [trailerOpen]);

  if (error) {
    return (
      <AppShell
        className="title-page title-detail-skinned"
        testId="title-detail-page"
        variant="sticky"
        leading={<BackLink fallbackTo={ROUTES.explore} testId="title-detail-back" />}
      >
        <p className="error">{error}</p>
      </AppShell>
    );
  }
  if (!detail) {
    return (
      <AppShell
        className="title-page title-detail-skinned"
        testId="title-detail-page"
        variant="sticky"
        leading={<BackLink fallbackTo={ROUTES.explore} testId="title-detail-back" />}
      >
        <p className="title-detail-loading">Loading…</p>
      </AppShell>
    );
  }

  const trailerKey = String(detail.trailer_youtube_key || "").trim();
  const plexHref =
    String(detail.plex_watch_url || "").trim() ||
    (canWatchOnPlex(detail) ? plexWatchUrl(detail.rating_key, detail.plex_machine_id || "") : "");
  const whyReason = displayRecommendationReason(detail.recommendation_reason);
  const showWhy = Boolean(whyReason);
  const purgeNote = String(detail.purge_reason || "").trim();
  const runtimeLabel = detail.runtime_minutes ? `${detail.runtime_minutes} mins` : null;
  const sizeLabel = formatFileSize(detail.file_size_bytes);
  const showNeighbors = Array.isArray(neighbors) && neighbors.length > 0;
  const tvProgress = detail.media_type === "show" ? formatTvProgress(detail) : null;
  const reviewsCta = reviewsCtaForDetail(detail);
  const releaseDateLabel = formatReleaseDate(
    detail.media_type === "show"
      ? detail.first_air_date || detail.release_date
      : detail.release_date || detail.first_air_date,
  );

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
    (c) =>
      String(c.job || "") !== "Director" && String(c.department || "") !== "Directing",
  );
  const directorCredit = directorCredits[0] || null;
  const genreChips = Array.isArray(detail.genres) ? detail.genres.slice(0, 2) : [];
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
  const addCtaLabel = canRequestSeerr
    ? "Request in Seerr"
    : canAddSonarr
      ? "Add to Sonarr"
      : "Add to Radarr";

  function scrollCarousel(dir) {
    const node = carouselRef.current;
    if (!node) return;
    node.scrollBy({ left: dir * 320, behavior: "smooth" });
  }

  return (
    <AppShell
      className="title-page title-detail-skinned"
      testId="title-detail-page"
      variant="sticky"
      leading={<BackLink fallbackTo={ROUTES.explore} testId="title-detail-back" />}
      actions={
        <span className="title-detail-sticky-label">
          {detail.media_type === "movie" ? "Movie" : "TV Show"}
        </span>
      }
    >
      <section
        className="title-detail-hero"
        style={detail.backdrop_url ? { "--title-backdrop": `url(${detail.backdrop_url})` } : undefined}
        data-testid="title-detail-hero"
      >
        <div className="title-detail-hero-scrim" aria-hidden="true" />
        <div className="title-detail-hero-inner">
          <div className="title-detail-chips">
            {detail.year ? <span className="title-chip">{detail.year}</span> : null}
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
              <span className="title-chip">TMDB {Number(detail.rating).toFixed(1)}</span>
            ) : null}
          </div>
          <h1 className="title-detail-headline">{detail.title}</h1>
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
                onClick={() => setTrailerOpen(true)}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  play_arrow
                </span>
                Trailer
              </button>
            ) : null}
            {reviewsCta?.kind === "rate" ? (
              <Link
                to={rateFlowHref()}
                className="title-cta title-cta-ghost"
                data-testid="title-reviews-cta"
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  rate_review
                </span>
                {reviewsCta.label}
              </Link>
            ) : null}
            {canAddOrRequest ? (
              <button
                type="button"
                className={`title-cta ${plexHref ? "title-cta-ghost" : "title-cta-primary"}`}
                data-testid="title-detail-add-button"
                disabled={addStatus === "loading" || addStatus === "success"}
                onClick={handleRequestAdd}
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
                onClick={() => setRecommendOpen(true)}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  person_add
                </span>
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
            <MetaTile label="Decade" value={decadeLabel(detail.year)} />
            <MetaTile label="Collection" value={detail.collection_name || null} />
            {tvProgress ? (
              <MetaTile label="Progress" value={tvProgress.label} />
            ) : null}
            {reviewsCta?.kind === "rated" ? (
              <MetaTile label="Your rating" value={reviewsCta.label.replace(/^Your rating:\s*/, "")} />
            ) : null}
            <MetaTile label="Rating" value={detail.content_rating || null} />
            <MetaTile
              label="Language"
              value={detail.original_language ? detail.original_language.toUpperCase() : null}
            />
            <MetaTile
              label="Countries"
              value={
                Array.isArray(detail.countries) && detail.countries.length
                  ? detail.countries.slice(0, 4).join(", ")
                  : null
              }
            />
            <MetaTile label="Status" value={detail.status || null} />
            {directorCredit ? (
              <div className="title-meta-tile">
                <span className="title-meta-tile-label">Director</span>
                <CreditLink
                  credit={directorCredit}
                  className="title-meta-tile-value title-credit-link"
                  testId="title-director-link"
                >
                  {directorCredit.name}
                </CreditLink>
              </div>
            ) : null}
            {genreChips.length ? (
              <div className="title-meta-tile">
                <span className="title-meta-tile-label">Genre</span>
                <span className="title-meta-tile-value title-genre-links">
                  {genreChips.map((genre, index) => (
                    <span key={genre}>
                      {index > 0 ? " · " : null}
                      <Link
                        to={exploreGenrePath(genre)}
                        className="title-credit-link"
                        data-testid="title-genre-link"
                      >
                        {genre}
                      </Link>
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
            <MetaTile
              label="Type"
              value={detail.media_type === "movie" ? "Movie" : "TV Show"}
            />
          </div>

          {detail.keywords?.length ? (
            <div className="title-detail-section">
              <h2 className="title-detail-section-label">Tags</h2>
              <div className="title-tag-list">
                {detail.keywords.slice(0, 8).map((tag) => {
                  const to = tagPath(tag);
                  return to ? (
                    <Link key={tag} to={to} className="title-tag title-tag-link" data-testid="title-tag-link">
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
                {castCredits.slice(0, 6).map((credit) => (
                  <li key={`${credit.tmdb_person_id || credit.name}-${credit.character || ""}`}>
                    <CreditLink
                      credit={credit}
                      className="title-credit-link"
                      testId="title-cast-link"
                    >
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

      {collectionPeers.length ? (
        <section className="title-neighbors title-collection-rail" data-testid="title-collection-rail">
          <div className="title-neighbors-header">
            <h2>More in {detail.collection_name}</h2>
          </div>
          <div className="title-neighbors-track">
            {collectionPeers.map((item) => {
              const path = titleDetailPath(item);
              const card = (
                <>
                  <div className="title-neighbor-poster">
                    {item.poster_url ? (
                      <img src={item.poster_url} alt="" loading="lazy" />
                    ) : (
                      <div className="poster-fallback">{item.title?.slice(0, 1) || "?"}</div>
                    )}
                  </div>
                  <h3>{item.title}</h3>
                  {item.year ? <p className="title-neighbor-year">{item.year}</p> : null}
                </>
              );
              return path ? (
                <Link
                  key={`${item.media_type}-${item.tmdb_id || item.rating_key || item.title}`}
                  to={path}
                  className="title-neighbor-card"
                  data-testid="title-collection-peer"
                >
                  {card}
                </Link>
              ) : (
                <div
                  key={`${item.media_type}-${item.title}`}
                  className="title-neighbor-card"
                  data-testid="title-collection-peer"
                >
                  {card}
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

      {showNeighbors ? (
        <section className="title-neighbors" data-testid="title-neighbors">
          <div className="title-neighbors-header">
            <h2>More Like This</h2>
            <div className="title-neighbors-controls">
              <div className="title-neighbors-modes" role="group" aria-label="Neighbor ranking">
                <button
                  type="button"
                  className={`ghost title-neighbors-mode${neighborMode === "similar" ? " is-active" : ""}`}
                  data-testid="title-neighbors-similar"
                  aria-pressed={neighborMode === "similar"}
                  onClick={() => setNeighborMode("similar")}
                >
                  Similar
                </button>
                <button
                  type="button"
                  className={`ghost title-neighbors-mode${neighborMode === "surprising" ? " is-active" : ""}`}
                  data-testid="title-neighbors-surprising"
                  aria-pressed={neighborMode === "surprising"}
                  onClick={() => setNeighborMode("surprising")}
                >
                  Surprising
                </button>
              </div>
              <button
                type="button"
                className="ghost title-neighbors-nav"
                aria-label="Scroll left"
                onClick={() => scrollCarousel(-1)}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  chevron_left
                </span>
              </button>
              <button
                type="button"
                className="ghost title-neighbors-nav"
                aria-label="Scroll right"
                onClick={() => scrollCarousel(1)}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  chevron_right
                </span>
              </button>
            </div>
          </div>
          <div className="title-neighbors-track" ref={carouselRef}>
            {neighbors.map((item) => {
              const path = titleDetailPath(item);
              const card = (
                <>
                  <div className="title-neighbor-poster">
                    {item.poster_url ? (
                      <img src={item.poster_url} alt="" loading="lazy" />
                    ) : (
                      <div className="poster-fallback">{item.title?.slice(0, 1) || "?"}</div>
                    )}
                  </div>
                  <h3>{item.title}</h3>
                  {item.year ? <p className="title-neighbor-year">{item.year}</p> : null}
                </>
              );
              return path ? (
                <Link key={`${item.media_type}-${item.tmdb_id || item.rating_key || item.title}`} to={path} className="title-neighbor-card">
                  {card}
                </Link>
              ) : (
                <div key={`${item.media_type}-${item.title}`} className="title-neighbor-card">
                  {card}
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

      {trailerOpen && trailerKey ? (
        <div
          className="trailer-modal-backdrop"
          data-testid="trailer-modal"
          onClick={() => setTrailerOpen(false)}
        >
          <div
            className="trailer-modal"
            role="dialog"
            aria-modal="true"
            aria-label={`Trailer for ${detail.title}`}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="trailer-modal-header">
              <h2>Trailer</h2>
              <button
                type="button"
                className="ghost"
                data-testid="close-trailer-modal"
                onClick={() => setTrailerOpen(false)}
              >
                Close
              </button>
            </div>
            <div className="trailer-modal-frame">
              <iframe
                title={`${detail.title} trailer`}
                src={`https://www.youtube.com/embed/${encodeURIComponent(trailerKey)}?autoplay=1&rel=0`}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />
            </div>
          </div>
        </div>
      ) : null}

      <RecommendModal
        item={detail}
        open={recommendOpen}
        onClose={() => setRecommendOpen(false)}
      />
    </AppShell>
  );
}

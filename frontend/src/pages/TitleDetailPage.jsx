import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import BackLink from "../components/BackLink";
import { getTitleRelations } from "../api/client";
import BulkLibraryDeleteDialog from "../components/BulkLibraryDeleteDialog.jsx";
import MarkBadMediaDialog from "../components/MarkBadMediaDialog.jsx";
import RemovalSummaryDialog from "../components/RemovalSummaryDialog.jsx";
import PosterOverlayControls from "../components/PosterOverlayControls";
import RecommendModal from "../components/RecommendModal";
import TitleDetailContent from "../components/TitleDetailContent";
import TitleDetailLink from "../components/TitleDetailLink";
import TitleReviewModal from "../components/TitleReviewModal";
import AppShell from "../layouts/AppShell";
import { useTitleDetail } from "../hooks/useTitleDetail.js";
import { useTitleDetailInteractions } from "../hooks/useTitleDetailInteractions.js";
import { resolveBackTarget, ROUTES } from "../lib/backNav.js";
import {
  canOwnerDeleteLibraryTitle,
  LIBRARY_DELETE_NOTICE_KEY,
} from "../lib/bulkLibraryDelete.js";
import { relationWhyCopy, relatedTitlesPath } from "../lib/relationUx.js";
import { titleDetailPath } from "../lib/titleLinks.js";

function TitleNeighborCard({ item, testId, why = null }) {
  // Both endpoint sources are library relations; make that explicit because
  // the compact relation payloads do not consistently include in_library.
  const libraryItem = { ...item, in_library: true };
  const path = titleDetailPath(libraryItem);
  const poster = libraryItem.poster_url ? (
    <img src={libraryItem.poster_url} alt="" loading="lazy" />
  ) : (
    <div className="poster-fallback">{libraryItem.title?.slice(0, 1) || "?"}</div>
  );

  return (
    <article className="title-neighbor-card" data-testid={testId}>
      <div className="title-neighbor-poster">
        {path ? (
          <TitleDetailLink item={libraryItem} className="title-neighbor-poster-link">
            {poster}
          </TitleDetailLink>
        ) : (
          poster
        )}
        <PosterOverlayControls item={libraryItem} testPrefix="title-neighbor" />
      </div>
      <h3>
        {path ? <TitleDetailLink item={libraryItem}>{libraryItem.title}</TitleDetailLink> : libraryItem.title}
      </h3>
      {libraryItem.year ? <p className="title-neighbor-year">{libraryItem.year}</p> : null}
      {why?.label ? (
        <p className="title-neighbor-why" data-testid={`${testId}-why`}>
          {why.label}
          {why.detail ? <span className="title-neighbor-why-detail"> · {why.detail}</span> : null}
        </p>
      ) : null}
    </article>
  );
}

export default function TitleDetailPage() {
  const { mediaType, itemId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const idType = searchParams.get("id_type") || "tmdb";
  const [relations, setRelations] = useState(null);
  const [neighborMode, setNeighborMode] = useState("similar");
  const [trailerOpen, setTrailerOpen] = useState(false);
  const [recommendOpen, setRecommendOpen] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const carouselRef = useRef(null);

  const { detail, setDetail, error, loading } = useTitleDetail({
    mediaType,
    itemId,
    idType,
    enabled: true,
  });

  const interactions = useTitleDetailInteractions({
    detail,
    setDetail,
    onDeleted: ({ notice }) => {
      const backTo = resolveBackTarget(location.state, ROUTES.chat);
      const prevState =
        location.state && typeof location.state === "object" ? { ...location.state } : {};
      navigate(backTo, {
        replace: true,
        state: {
          ...prevState,
          [LIBRARY_DELETE_NOTICE_KEY]: notice,
        },
      });
    },
  });

  useEffect(() => {
    let cancelled = false;
    getTitleRelations(mediaType, itemId, { idType, limit: 50 })
      .then((data) => {
        if (!cancelled) setRelations(Array.isArray(data?.items) ? data.items : []);
      })
      .catch(() => {
        if (!cancelled) setRelations([]);
      });
    return () => {
      cancelled = true;
    };
  }, [mediaType, itemId, idType]);

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
        leading={<BackLink fallbackTo={ROUTES.chat} testId="title-detail-back" />}
      >
        <p className="error">{error}</p>
      </AppShell>
    );
  }
  if (loading || !detail) {
    return (
      <AppShell
        className="title-page title-detail-skinned"
        testId="title-detail-page"
        variant="sticky"
        leading={<BackLink fallbackTo={ROUTES.chat} testId="title-detail-back" />}
      >
        <p className="title-detail-loading">Loading…</p>
      </AppShell>
    );
  }

  const trailerKey = String(detail.trailer_youtube_key || "").trim();
  const collectionEdges = (relations || []).filter((edge) => edge.relation === "collection");
  const crewEdges = (relations || []).filter((edge) => edge.relation === "shared_crew");
  const plotEdges = (relations || []).filter((edge) => edge.relation === "neighbor");
  const neighbors =
    neighborMode === "surprising"
      ? plotEdges.filter((edge) => edge.why?.surprise_flavor)
      : plotEdges;
  const showNeighbors = plotEdges.length > 0;
  const relatedPath = relatedTitlesPath(detail);
  const canDeleteLibrary = canOwnerDeleteLibraryTitle(detail, {
    role: interactions.userRole,
    multiUserEnabled: interactions.multiUserEnabled,
  });

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
      leading={<BackLink fallbackTo={ROUTES.chat} testId="title-detail-back" />}
      actions={
        <span className="title-detail-sticky-label">
          {detail.media_type === "movie" ? "Movie" : "TV Show"}
        </span>
      }
    >
      <TitleDetailContent
        detail={detail}
        variant="full"
        multiUserEnabled={interactions.multiUserEnabled}
        userRole={interactions.userRole}
        requestPath={interactions.requestPath}
        addStatus={interactions.addStatus}
        addMessage={interactions.addMessage}
        watchStatus={interactions.watchStatus}
        watchMessage={interactions.watchMessage}
        deleting={interactions.deleting}
        markingBadMedia={interactions.badMediaLoading}
        badMediaMessage={interactions.badMediaMessage}
        onRequestAdd={interactions.handleRequestAdd}
        onToggleWatched={interactions.handleToggleWatched}
        onOpenTrailer={() => setTrailerOpen(true)}
        onOpenReview={() => setReviewOpen(true)}
        onOpenRecommend={() => setRecommendOpen(true)}
        onOpenDelete={interactions.openLibraryDelete}
        onOpenMarkBadMedia={interactions.openMarkBadMedia}
      />

      <section className="title-relations-entry" data-testid="title-relations-entry">
        <div>
          <h2>Title connections</h2>
          <p>Follow this title through collections, shared filmmakers, and plot kinship.</p>
        </div>
        <Link to={relatedPath} className="title-cta title-cta-ghost title-relations-cta">
          Related titles
          <span className="material-symbols-outlined" aria-hidden="true">
            arrow_forward
          </span>
        </Link>
      </section>

      {Array.isArray(relations) && !relations.length ? (
        <p className="title-relations-cold-note status status-secondary">
          Connections are still warming up for this title. The background library refresh may
          add them later.
        </p>
      ) : null}

      {collectionEdges.length ? (
        <section className="title-neighbors title-collection-rail" data-testid="title-collection-rail">
          <div className="title-neighbors-header">
            <h2>
              More in{" "}
              {detail.collection_name ||
                collectionEdges[0]?.why?.collection_name ||
                "this collection"}
            </h2>
          </div>
          <div className="title-neighbors-track">
            {collectionEdges.map((edge) => (
              <TitleNeighborCard
                key={`${edge.relation}-${edge.to_id}`}
                item={edge.peer}
                testId="title-collection-peer"
                why={relationWhyCopy(edge.why)}
              />
            ))}
          </div>
        </section>
      ) : null}

      {crewEdges.length ? (
        <section className="title-neighbors title-crew-rail" data-testid="title-crew-rail">
          <div className="title-neighbors-header">
            <h2>Shared cast &amp; crew</h2>
          </div>
          <div className="title-neighbors-track">
            {crewEdges.map((edge) => (
              <TitleNeighborCard
                key={`${edge.relation}-${edge.to_id}`}
                item={edge.peer}
                testId="title-crew-peer"
                why={relationWhyCopy(edge.why)}
              />
            ))}
          </div>
        </section>
      ) : null}

      {showNeighbors ? (
        <section
          className={`title-neighbors${neighborMode === "surprising" ? " title-neighbors--surprising" : ""}`}
          data-testid="title-neighbors"
        >
          <div className="title-neighbors-header">
            <h2>{neighborMode === "surprising" ? "Surprisingly similar" : "Similar plot"}</h2>
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
          {neighborMode === "surprising" ? (
            <p className="title-neighbors-intro" data-testid="title-neighbors-surprise-intro">
              Strong plot kinship with little overlap in genre, keyword, or filmmaker labels.
            </p>
          ) : null}
          {neighborMode === "surprising" && !neighbors.length ? (
            <p className="title-neighbors-intro">
              No surprising connection is ready yet. Similar plot matches are still available.
            </p>
          ) : null}
          <div className="title-neighbors-track" ref={carouselRef}>
            {neighbors.map((edge) => (
              <TitleNeighborCard
                key={`${edge.relation}-${edge.to_id}`}
                item={edge.peer}
                testId="title-neighbor-card"
                why={relationWhyCopy(edge.why)}
              />
            ))}
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
              <div className="trailer-modal-actions">
                <a
                  className="btn-link ghost"
                  href={`https://www.youtube.com/watch?v=${encodeURIComponent(trailerKey)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Open on YouTube
                </a>
                <button
                  type="button"
                  className="ghost"
                  data-testid="close-trailer-modal"
                  onClick={() => setTrailerOpen(false)}
                >
                  Close
                </button>
              </div>
            </div>
            <div className="trailer-modal-frame">
              <iframe
                title={`${detail.title} trailer`}
                src={`https://www.youtube-nocookie.com/embed/${encodeURIComponent(trailerKey)}?autoplay=1&rel=0`}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen"
                referrerPolicy="strict-origin-when-cross-origin"
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

      <TitleReviewModal
        detail={detail}
        open={reviewOpen}
        onClose={() => setReviewOpen(false)}
        onSaved={(saved) => {
          setDetail((prev) =>
            prev
              ? {
                  ...prev,
                  user_stars: saved?.stars ?? prev.user_stars,
                }
              : prev,
          );
        }}
      />

      <BulkLibraryDeleteDialog
        open={interactions.deleteOpen}
        titles={canDeleteLibrary ? [detail.title || "Untitled"] : []}
        loading={interactions.deleting}
        error={interactions.deleteError}
        onCancel={() => {
          if (interactions.deleting) return;
          interactions.setDeleteOpen(false);
          interactions.setDeleteError("");
        }}
        onConfirm={interactions.handleLibraryDeleteConfirm}
      />

      <MarkBadMediaDialog
        open={interactions.badMediaOpen}
        title={detail?.title || "Untitled"}
        mediaType={detail?.media_type || "movie"}
        loading={interactions.badMediaLoading}
        error={interactions.badMediaError}
        onCancel={() => {
          if (interactions.badMediaLoading) return;
          interactions.setBadMediaOpen(false);
        }}
        onConfirm={interactions.handleMarkBadMediaConfirm}
      />

      <RemovalSummaryDialog
        open={Boolean(interactions.removalSummary)}
        result={interactions.removalSummary}
        onClose={interactions.dismissRemovalSummary}
      />
    </AppShell>
  );
}

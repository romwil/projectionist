import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import BackLink from "../components/BackLink";
import { api, queryLibrary } from "../api/client";
import BulkLibraryDeleteDialog from "../components/BulkLibraryDeleteDialog.jsx";
import RecommendModal from "../components/RecommendModal";
import TitleDetailContent from "../components/TitleDetailContent";
import TitleReviewModal from "../components/TitleReviewModal";
import AppShell from "../layouts/AppShell";
import { useTitleDetail } from "../hooks/useTitleDetail.js";
import { useTitleDetailInteractions } from "../hooks/useTitleDetailInteractions.js";
import { resolveBackTarget } from "../lib/backNav.js";
import { ROUTES } from "../lib/browseLinks.js";
import {
  canOwnerDeleteLibraryTitle,
  LIBRARY_DELETE_NOTICE_KEY,
} from "../lib/bulkLibraryDelete.js";
import { filterCollectionPeers } from "../lib/titleDetailExtras.js";
import { titleDetailPath } from "../lib/titleLinks.js";

export default function TitleDetailPage() {
  const { mediaType, itemId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const idType = searchParams.get("id_type") || "tmdb";
  const [neighbors, setNeighbors] = useState(null);
  const [neighborMode, setNeighborMode] = useState("similar");
  const [trailerOpen, setTrailerOpen] = useState(false);
  const [recommendOpen, setRecommendOpen] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [collectionPeers, setCollectionPeers] = useState([]);
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
      const backTo = resolveBackTarget(location.state, ROUTES.explore);
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
  if (loading || !detail) {
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
  const showNeighbors = Array.isArray(neighbors) && neighbors.length > 0;
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
      leading={<BackLink fallbackTo={ROUTES.explore} testId="title-detail-back" />}
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
        onRequestAdd={interactions.handleRequestAdd}
        onToggleWatched={interactions.handleToggleWatched}
        onOpenTrailer={() => setTrailerOpen(true)}
        onOpenReview={() => setReviewOpen(true)}
        onOpenRecommend={() => setRecommendOpen(true)}
        onOpenDelete={interactions.openLibraryDelete}
      />

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
    </AppShell>
  );
}

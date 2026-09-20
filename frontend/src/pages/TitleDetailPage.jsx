import { useEffect, useState } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import BackLink from "../components/BackLink";
import BulkLibraryDeleteDialog from "../components/BulkLibraryDeleteDialog.jsx";
import MarkBadMediaDialog from "../components/MarkBadMediaDialog.jsx";
import RemovalSummaryDialog from "../components/RemovalSummaryDialog.jsx";
import RecommendModal from "../components/RecommendModal";
import TitleDetailContent from "../components/TitleDetailContent";
import TitleNeighborsRails from "../components/TitleNeighborsRails";
import TitleReviewModal from "../components/TitleReviewModal";
import AppShell from "../layouts/AppShell";
import { useTitleDetail } from "../hooks/useTitleDetail.js";
import { useTitleDetailInteractions } from "../hooks/useTitleDetailInteractions.js";
import { resolveBackTarget, ROUTES } from "../lib/backNav.js";
import {
  canOwnerDeleteLibraryTitle,
  LIBRARY_DELETE_NOTICE_KEY,
} from "../lib/bulkLibraryDelete.js";

export default function TitleDetailPage() {
  const { mediaType, itemId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const idType = searchParams.get("id_type") || "tmdb";
  const [trailerOpen, setTrailerOpen] = useState(false);
  const [recommendOpen, setRecommendOpen] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);

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
  const canDeleteLibrary = canOwnerDeleteLibraryTitle(detail, {
    role: interactions.userRole,
    multiUserEnabled: interactions.multiUserEnabled,
  });

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

      <TitleNeighborsRails
        mediaType={mediaType}
        itemId={itemId}
        idType={idType}
        detail={detail}
        showConnectionsEntry
      />

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

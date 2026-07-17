import { useEffect, useId, useRef, useState } from "react";
import BulkLibraryDeleteDialog from "./BulkLibraryDeleteDialog.jsx";
import RecommendModal from "./RecommendModal";
import TitleDetailContent from "./TitleDetailContent";
import TitleReviewModal from "./TitleReviewModal";
import { useTitleDetail } from "../hooks/useTitleDetail.js";
import { useTitleDetailInteractions } from "../hooks/useTitleDetailInteractions.js";
import { canOwnerDeleteLibraryTitle } from "../lib/bulkLibraryDelete.js";
import { titleDetailHrefFromTarget } from "../lib/titleDetailDrawer.js";

function getFocusableElements(root) {
  if (!root) return [];
  return [
    ...root.querySelectorAll(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ];
}

/**
 * Right-docked slide-over for in-context title detail (reusable from lists).
 * Pass `target`: { mediaType, itemId, idType } from titleDetailTargetFromItem().
 */
export default function TitleDetailDrawer({
  open,
  target,
  onClose,
  returnFocusRef,
  onDeleted,
}) {
  const panelRef = useRef(null);
  const closeButtonRef = useRef(null);
  const titleId = useId();
  const [trailerOpen, setTrailerOpen] = useState(false);
  const [recommendOpen, setRecommendOpen] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);

  const mediaType = target?.mediaType;
  const itemId = target?.itemId;
  const idType = target?.idType || "tmdb";

  const { detail, setDetail, error, loading } = useTitleDetail({
    mediaType,
    itemId,
    idType,
    enabled: open && Boolean(target),
  });

  const interactions = useTitleDetailInteractions({
    detail,
    setDetail,
    onDeleted: (result) => {
      onDeleted?.(result);
      onClose?.();
    },
  });

  const fullPageHref = titleDetailHrefFromTarget(target);
  const trailerKey = String(detail?.trailer_youtube_key || "").trim();

  useEffect(() => {
    if (!open) {
      setTrailerOpen(false);
      setRecommendOpen(false);
      setReviewOpen(false);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;

    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const focusTimer = window.setTimeout(() => {
      closeButtonRef.current?.focus();
    }, 0);

    function onKeyDown(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose?.();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = getFocusableElements(panelRef.current);
      if (!focusable.length) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      const returnNode = returnFocusRef?.current;
      if (returnNode && typeof returnNode.focus === "function") {
        returnNode.focus();
      } else if (previousFocus && typeof previousFocus.focus === "function") {
        previousFocus.focus();
      }
    };
  }, [open, onClose, returnFocusRef]);

  useEffect(() => {
    if (!trailerOpen) return undefined;
    function onKey(event) {
      if (event.key === "Escape") setTrailerOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [trailerOpen]);

  if (!open) return null;

  const canDeleteLibrary = canOwnerDeleteLibraryTitle(detail, {
    role: interactions.userRole,
    multiUserEnabled: interactions.multiUserEnabled,
  });

  return (
    <>
      <button
        type="button"
        className="title-detail-drawer-scrim"
        data-testid="title-detail-drawer-scrim"
        aria-label="Close title detail"
        onClick={onClose}
      />

      <aside
        ref={panelRef}
        className="title-detail-drawer-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        data-testid="title-detail-drawer"
      >
        <header className="title-detail-drawer-header">
          <p className="title-detail-drawer-eyebrow">
            {detail?.media_type === "show" ? "TV Show" : "Movie"}
          </p>
          <button
            ref={closeButtonRef}
            type="button"
            className="title-detail-drawer-close ghost"
            data-testid="title-detail-drawer-close"
            aria-label="Close"
            onClick={onClose}
          >
            <span className="material-symbols-outlined" aria-hidden="true">
              close
            </span>
          </button>
        </header>

        <div className="title-detail-drawer-body">
          {loading ? (
            <div className="title-detail-drawer-loading" aria-live="polite">
              <div className="dash-skeleton" aria-label="Loading title">
                <div className="dash-skeleton-bar" />
                <div className="dash-skeleton-bar short" />
                <div className="dash-skeleton-bar" />
              </div>
            </div>
          ) : error ? (
            <p className="error title-detail-drawer-error" role="alert">
              {error}
            </p>
          ) : detail ? (
            <TitleDetailContent
              detail={detail}
              variant="compact"
              fullPageHref={fullPageHref}
              titleId={titleId}
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
          ) : null}
        </div>
      </aside>

      {trailerOpen && trailerKey && detail ? (
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
        titles={canDeleteLibrary ? [detail?.title || "Untitled"] : []}
        loading={interactions.deleting}
        error={interactions.deleteError}
        onCancel={() => {
          if (interactions.deleting) return;
          interactions.setDeleteOpen(false);
          interactions.setDeleteError("");
        }}
        onConfirm={interactions.handleLibraryDeleteConfirm}
      />
    </>
  );
}

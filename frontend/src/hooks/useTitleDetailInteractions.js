import { useEffect, useRef, useState } from "react";
import {
  confirmAction,
  deleteLibraryItems,
  formatApiError,
  getFeatures,
  markBadMedia,
  proposeAction,
  setLibraryItemWatched,
} from "../api/client";
import {
  alreadyInArrMessage,
  buildProposeActionBody,
  isAlreadyInArr,
  normalizeUserRole,
  requestPathFromFeatures,
  resolveAddCapability,
  serviceLabelForTarget,
} from "../lib/addActions.js";
import {
  canOwnerDeleteLibraryTitle,
  formatLibraryDeleteSuccessMessage,
  hasRemovalSummary,
  libraryItemRatingKey,
} from "../lib/bulkLibraryDelete.js";
import { canMarkTitleWatched, isTitleWatched } from "../lib/titleDetailExtras.js";

function formatLibraryDeleteFailure(errorText) {
  const message = String(errorText || "").trim();
  if (!message) return "Could not fully remove this title.";
  const lower = message.toLowerCase();
  const notInArr =
    lower.includes("not in sonarr") ||
    lower.includes("not in radarr") ||
    (lower.includes("could not find") &&
      (lower.includes("sonarr") || lower.includes("radarr")));
  if (!notInArr) return message;
  return `${message} Files may already be gone. Choose Index only to clear the Projectionist row, or cancel and refresh Storage Intelligence.`;
}

/**
 * Shared add / watch / delete interactions for title detail surfaces.
 * `onDeleted` runs after a successful library delete (drawer closes, page navigates back).
 * Full removes with path/size detail show a summary first; dismiss then calls `onDeleted`.
 * `onDeleteSuccess` runs as soon as the API succeeds (list refresh) even when a summary is pending.
 */
export function useTitleDetailInteractions({ detail, setDetail, onDeleted, onDeleteSuccess }) {
  const [multiUserEnabled, setMultiUserEnabled] = useState(false);
  const [userRole, setUserRole] = useState("owner");
  const [requestPath, setRequestPath] = useState("arr");
  const [addStatus, setAddStatus] = useState(null);
  const [addMessage, setAddMessage] = useState("");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [removalSummary, setRemovalSummary] = useState(null);
  const [pendingDeletedPayload, setPendingDeletedPayload] = useState(null);
  const [badMediaOpen, setBadMediaOpen] = useState(false);
  const [badMediaLoading, setBadMediaLoading] = useState(false);
  const [badMediaError, setBadMediaError] = useState("");
  const [badMediaMessage, setBadMediaMessage] = useState("");
  const [watchStatus, setWatchStatus] = useState(null);
  const [watchMessage, setWatchMessage] = useState("");
  const deleteInFlightRef = useRef(false);

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
    // Do not clobber an in-flight delete when the drawer target briefly clears
    // (Escape / remount) — the request may still complete and needs honest UI.
    if (deleteInFlightRef.current) return;
    setAddStatus(null);
    setAddMessage("");
    setDeleteOpen(false);
    setDeleting(false);
    setDeleteError("");
    setRemovalSummary(null);
    setPendingDeletedPayload(null);
    setBadMediaOpen(false);
    setBadMediaLoading(false);
    setBadMediaError("");
    setBadMediaMessage("");
    setWatchStatus(null);
    setWatchMessage("");
  }, [detail?.rating_key, detail?.tmdb_id, detail?.title]);

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

  function openLibraryDelete() {
    if (!canOwnerDeleteLibraryTitle(detail, { role: userRole, multiUserEnabled })) return;
    if (deleteInFlightRef.current) return;
    setDeleteError("");
    setDeleteOpen(true);
  }

  async function handleLibraryDeleteConfirm({ mode } = {}) {
    if (deleteInFlightRef.current || deleting) return;
    if (!canOwnerDeleteLibraryTitle(detail, { role: userRole, multiUserEnabled })) return;
    const ratingKey = libraryItemRatingKey(detail);
    if (!ratingKey) return;
    deleteInFlightRef.current = true;
    setDeleting(true);
    setDeleteError("");
    try {
      const result = await deleteLibraryItems([ratingKey], { mode });
      const errors = Array.isArray(result?.errors) ? result.errors : [];
      if (errors.length && !(Number(result?.deleted) > 0)) {
        setDeleteError(formatLibraryDeleteFailure(errors[0]?.error));
        deleteInFlightRef.current = false;
        setDeleting(false);
        return;
      }
      const notice = formatLibraryDeleteSuccessMessage({
        deleted: Number(result?.deleted) || 0,
        title: detail.title,
        mode: result?.mode || mode,
        errorCount: errors.length,
      });
      const payload = { notice, detail, result };
      setDeleteOpen(false);
      setDeleting(false);
      deleteInFlightRef.current = false;
      // Refresh lists immediately so Storage Intelligence / browse do not keep
      // stale rows while the removal summary is still open.
      onDeleteSuccess?.(payload);
      if (hasRemovalSummary(result)) {
        setRemovalSummary(result);
        setPendingDeletedPayload(payload);
        return;
      }
      onDeleted?.(payload);
    } catch (err) {
      setDeleteError(
        formatApiError(err) || "Could not delete this title from the library index.",
      );
      deleteInFlightRef.current = false;
      setDeleting(false);
    }
  }

  function dismissRemovalSummary() {
    const payload = pendingDeletedPayload;
    setRemovalSummary(null);
    setPendingDeletedPayload(null);
    if (payload) onDeleted?.(payload);
  }

  function openMarkBadMedia() {
    if (!canOwnerDeleteLibraryTitle(detail, { role: userRole, multiUserEnabled })) return;
    setBadMediaError("");
    setBadMediaMessage("");
    setBadMediaOpen(true);
  }

  async function handleMarkBadMediaConfirm() {
    if (badMediaLoading) return;
    if (!canOwnerDeleteLibraryTitle(detail, { role: userRole, multiUserEnabled })) return;
    const ratingKey = libraryItemRatingKey(detail);
    setBadMediaLoading(true);
    setBadMediaError("");
    try {
      const result = await markBadMedia({
        rating_key: ratingKey || undefined,
        tmdb_id: detail?.tmdb_id ?? undefined,
        tvdb_id: detail?.tvdb_id ?? undefined,
        media_type: detail?.media_type || undefined,
      });
      setBadMediaOpen(false);
      const action = String(result?.action || "replace");
      const files = Number(result?.files_removed) || 0;
      setBadMediaMessage(
        files > 0
          ? `Asked ${detail?.media_type === "show" ? "Sonarr" : "Radarr"} to replace the bad file (${action}). No exclusion added.`
          : `Asked ${detail?.media_type === "show" ? "Sonarr" : "Radarr"} to search for a replacement (${action}). No exclusion added.`,
      );
    } catch (err) {
      setBadMediaError(formatApiError(err) || "Could not mark media for replacement.");
    } finally {
      setBadMediaLoading(false);
    }
  }

  async function handleToggleWatched() {
    if (!canMarkTitleWatched(detail, { role: userRole, multiUserEnabled })) return;
    const ratingKey = libraryItemRatingKey(detail);
    if (!ratingKey || watchStatus === "loading") return;
    const nextWatched = !isTitleWatched(detail);
    setWatchStatus("loading");
    setWatchMessage("");
    try {
      const result = await setLibraryItemWatched(ratingKey, nextWatched);
      setDetail((prev) =>
        prev
          ? {
              ...prev,
              view_count: result.view_count,
              last_viewed_at: result.last_viewed_at,
            }
          : prev,
      );
      setWatchStatus("success");
      const plexNote =
        result.plex_synced === false
          ? result.plex_reason === "plex_not_configured"
            ? " (local only — Plex not configured)"
            : result.plex_reason === "plex_error"
              ? " (local saved; Plex sync failed)"
              : " (local only)"
          : "";
      setWatchMessage(
        nextWatched ? `Marked as watched${plexNote}.` : `Marked as unwatched${plexNote}.`,
      );
    } catch (err) {
      setWatchStatus("error");
      setWatchMessage(formatApiError(err) || "Could not update watched state.");
    }
  }

  return {
    multiUserEnabled,
    userRole,
    requestPath,
    addStatus,
    addMessage,
    deleteOpen,
    setDeleteOpen,
    deleting,
    deleteError,
    setDeleteError,
    removalSummary,
    dismissRemovalSummary,
    badMediaOpen,
    setBadMediaOpen,
    badMediaLoading,
    badMediaError,
    badMediaMessage,
    openMarkBadMedia,
    handleMarkBadMediaConfirm,
    watchStatus,
    watchMessage,
    handleRequestAdd,
    openLibraryDelete,
    handleLibraryDeleteConfirm,
    handleToggleWatched,
  };
}

import { useEffect, useState } from "react";
import {
  confirmAction,
  deleteLibraryItems,
  formatApiError,
  getFeatures,
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
  libraryItemRatingKey,
} from "../lib/bulkLibraryDelete.js";
import { canMarkTitleWatched, isTitleWatched } from "../lib/titleDetailExtras.js";

/**
 * Shared add / watch / delete interactions for title detail surfaces.
 * `onDeleted` runs after a successful library delete (drawer closes, page navigates back).
 */
export function useTitleDetailInteractions({ detail, setDetail, onDeleted }) {
  const [multiUserEnabled, setMultiUserEnabled] = useState(false);
  const [userRole, setUserRole] = useState("owner");
  const [requestPath, setRequestPath] = useState("arr");
  const [addStatus, setAddStatus] = useState(null);
  const [addMessage, setAddMessage] = useState("");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [watchStatus, setWatchStatus] = useState(null);
  const [watchMessage, setWatchMessage] = useState("");

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
    setAddStatus(null);
    setAddMessage("");
    setDeleteOpen(false);
    setDeleting(false);
    setDeleteError("");
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
    setDeleteError("");
    setDeleteOpen(true);
  }

  async function handleLibraryDeleteConfirm() {
    if (deleting) return;
    if (!canOwnerDeleteLibraryTitle(detail, { role: userRole, multiUserEnabled })) return;
    const ratingKey = libraryItemRatingKey(detail);
    if (!ratingKey) return;
    setDeleting(true);
    setDeleteError("");
    try {
      const result = await deleteLibraryItems([ratingKey]);
      const notice = formatLibraryDeleteSuccessMessage({
        deleted: Number(result?.deleted) || 0,
        title: detail.title,
      });
      onDeleted?.({ notice, detail });
    } catch (err) {
      setDeleteError(formatApiError(err) || "Could not delete this title from the library index.");
      setDeleting(false);
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
    watchStatus,
    watchMessage,
    handleRequestAdd,
    openLibraryDelete,
    handleLibraryDeleteConfirm,
    handleToggleWatched,
  };
}

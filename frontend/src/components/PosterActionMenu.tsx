import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { useAnchoredPopover } from "../hooks/useAnchoredPopover";
import {
  addCuratedListItem,
  addWatchlistPin,
  deleteLibraryItems,
  listCuratedLists,
  markBadMedia,
  setLibraryItemWatched,
} from "../api/client";
import MarkBadMediaDialog from "./MarkBadMediaDialog";
import { useConfirmModal } from "../hooks/useConfirmModal";
import { useAuthGate } from "./UserMenu";
import ReportMediaIssueModal from "./ReportMediaIssueModal";
import TitleDetailLink from "./TitleDetailLink";
import { chatAboutTitleHref, recommendLikeHref } from "../lib/backNav.js";
import {
  canWatchOnPlex,
  libraryWatchPath,
  plexPlayRatingKey,
  plexWatchUrl,
  titleDetailPath,
} from "../lib/titleLinks.js";
import { commitPosterWatched, posterWatchAction } from "../lib/posterWatchAction.js";
import { rememberContinueWatchingProgress } from "../lib/exploreHubCache.js";

function placePosterMenu(anchor: any, menu: any) {
  const margin = 8;
  const above = anchor.top - margin - menu.height;
  const below = anchor.bottom + margin;
  const top = above >= margin || below + menu.height > window.innerHeight
    ? Math.max(margin, Math.min(above, window.innerHeight - menu.height - margin))
    : Math.min(below, window.innerHeight - menu.height - margin);
  const left = Math.max(margin, Math.min(anchor.left, window.innerWidth - menu.width - margin));
  return { top: `${top}px`, left: `${left}px` };
}

/** Props for PosterActionMenu. `any` = API/handler bags until Wave 4 client generics. */
type PosterActionMenuProps = {
  item?: any;
  onRecommend?: (...args: any[]) => void;
  onSeed?: (...args: any[]) => void;
  onTogglePin?: (...args: any[]) => void;
  pinned?: boolean;
  onRemovedFromList?: (...args: any[]) => void;
  listId?: string;
  listItemId?: string;
  onRemoveFromList?: (...args: any[]) => void;
  onWatchedChange?: (...args: any[]) => void;
  motifWhy?: any;
};

export default function PosterActionMenu({
  item,
  onRecommend,
  onSeed,
  onTogglePin,
  pinned = false,
  onRemovedFromList,
  listId,
  listItemId,
  onRemoveFromList,
  onWatchedChange,
  motifWhy,
}: PosterActionMenuProps) {
  const { isOwner, multiUserEnabled, role } = useAuthGate();
  const { confirm, modal } = useConfirmModal();
  const [lists, setLists] = useState<any[]>([]);
  const [listOpen, setListOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [badMediaOpen, setBadMediaOpen] = useState(false);
  const [badMediaLoading, setBadMediaLoading] = useState(false);
  const [flash, setFlash] = useState("");
  const flashTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Optimistic overlay so the menu label + card reflect a completed scrobble
  // without waiting on a parent refresh.
  const [watchPatch, setWatchPatch] = useState<any | null>(null);
  const { open, setOpen, rootRef, popoverRef, popoverStyle } = useAnchoredPopover({
    closeOnEscape: true,
    anchorSelector: ".poster-action-grip",
    placement: placePosterMenu,
    repositionKey: `${listOpen}`,
  });
  const detailPath = titleDetailPath({ ...item, in_library: true });
  const playHref = canWatchOnPlex(item) ? libraryWatchPath(plexPlayRatingKey(item)) : "";
  const plexHref = item?.plex_watch_url || (canWatchOnPlex(item) ? plexWatchUrl(item.rating_key) : "");
  const effectiveItem = watchPatch ? { ...item, ...watchPatch } : item;
  const watchAction = posterWatchAction(effectiveItem, { role, multiUserEnabled });

  useEffect(() => {
    return () => {
      if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
    };
  }, []);

  function flashStatus(message: any) {
    setOpen(false);
    setListOpen(false);
    setFlash(message);
    if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
    flashTimerRef.current = setTimeout(() => setFlash(""), 2800);
  }

  async function openLists() {
    setListOpen(true);
    try {
      const payload = await listCuratedLists();
      setLists(payload?.items || payload || []);
    } catch (error: unknown) {
      flashStatus((error as { message?: string }).message || "Could not load lists.");
    }
  }

  async function addToList(list: any) {
    try {
      await addCuratedListItem(list.id, {
        tmdb_id: item?.tmdb_id || undefined,
        tvdb_id: item?.tvdb_id || undefined,
        media_type: item?.media_type,
        title: item?.title,
        library_item_id: item?.id && Number.isInteger(Number(item.id)) ? Number(item.id) : undefined,
      });
      flashStatus(`Added to ${list.name || "list"}.`);
    } catch (error: unknown) {
      flashStatus((error as { message?: string }).message || "Could not add to list.");
    }
  }

  async function togglePin() {
    try {
      if (onTogglePin) await onTogglePin(item);
      else await addWatchlistPin({ tmdb_id: item?.tmdb_id, tvdb_id: item?.tvdb_id, media_type: item?.media_type, title: item?.title });
      flashStatus(pinned ? "Removed from watchlist." : "Pinned to watchlist.");
    } catch (error: unknown) {
      flashStatus((error as { message?: string }).message || "Could not update watchlist.");
    }
  }

  async function toggleWatched() {
    if (!watchAction) return;
    const nextWatched = watchAction.nextWatched;
    try {
      const { patch, result } = await commitPosterWatched(effectiveItem, {
        watched: nextWatched,
        setWatched: setLibraryItemWatched,
        rememberProgress: rememberContinueWatchingProgress,
      });
      setWatchPatch(patch);
      onWatchedChange?.(item, patch, result);
      const plexNote =
        (result as any)?.plex_synced === false
          ? (result as any).plex_reason === "plex_not_configured"
            ? " (local only — Plex not configured)"
            : (result as any).plex_reason === "plex_error"
              ? " (saved locally; Plex sync failed)"
              : " (local only)"
          : "";
      flashStatus(nextWatched ? `Marked as watched${plexNote}.` : `Marked as unwatched${plexNote}.`);
    } catch (error: unknown) {
      flashStatus((error as { message?: string }).message || "Could not update watched state.");
    }
  }

  async function deleteIndex() {
    setOpen(false);
    if (
      !(await confirm({
        title: "Remove from index",
        body: `Remove "${item.title || "this title"}" from the Projectionist index? Plex files are not deleted.`,
        confirmLabel: "Remove",
        danger: true,
      }))
    ) {
      return;
    }
    try {
      await deleteLibraryItems([item.rating_key || item.plex_rating_key]);
      flashStatus("Removed from the Projectionist index.");
    } catch (error: unknown) {
      flashStatus((error as { message?: string }).message || "Could not remove title.");
    }
  }

  async function handleMarkBadMedia() {
    setBadMediaLoading(true);
    try {
      await markBadMedia({
        rating_key: item.rating_key || item.plex_rating_key || undefined,
        tmdb_id: item?.tmdb_id ?? undefined,
        tvdb_id: item?.tvdb_id ?? undefined,
        media_type: item?.media_type || undefined,
      });
      setBadMediaOpen(false);
      flashStatus("Asked Radarr/Sonarr to replace the bad file. No exclusion added.");
    } catch (error: unknown) {
      flashStatus((error as { message?: string }).message || "Could not mark media for replacement.");
    } finally {
      setBadMediaLoading(false);
    }
  }

  const popover = open && typeof document !== "undefined" ? createPortal(
    <div className="poster-action-popover" ref={popoverRef} role="menu" style={popoverStyle || { visibility: "hidden" }}>
      {detailPath ? (
        <TitleDetailLink className="poster-action-item" item={{ ...item, in_library: true }} onClick={() => setOpen(false)}>
          Open details
        </TitleDetailLink>
      ) : null}
      {playHref ? <Link className="poster-action-item" to={playHref} onClick={() => setOpen(false)}>Play</Link> : null}
      {plexHref ? <a className="poster-action-item" href={plexHref} target="_blank" rel="noopener noreferrer">Open in Plex</a> : null}
      {watchAction ? <button type="button" className="poster-action-item" onClick={toggleWatched}>{watchAction.label}</button> : null}
      <button type="button" className="poster-action-item" onClick={togglePin}>{pinned ? "Remove from watchlist" : "Add to watchlist"}</button>
      {listId && onRemoveFromList ? <button type="button" className="poster-action-item" onClick={async () => { await onRemoveFromList(listId, listItemId); onRemovedFromList?.(); flashStatus("Removed from this collection."); }}>Remove from this collection</button> : null}
      <button type="button" className="poster-action-item" onClick={openLists}>Add to list or playlist…</button>
      {listOpen ? <div className="poster-action-submenu">
        {lists.length ? lists.map((list) => <button key={list.id} type="button" className="poster-action-item" onClick={() => addToList(list)}>{list.name} <span>{list.list_kind === "playlist" ? "Playlist" : "List"}</span></button>) : <span className="poster-action-label">No lists yet</span>}
      </div> : null}
      {onRecommend && multiUserEnabled ? <button type="button" className="poster-action-item" onClick={() => { onRecommend(item); setOpen(false); }}>Recommend</button> : null}
      {item?.title ? <Link className="poster-action-item" to={recommendLikeHref(item)} onClick={() => setOpen(false)}>Recommend like this in chat</Link> : null}
      {item?.title ? <Link className="poster-action-item" to={chatAboutTitleHref(item)} onClick={() => setOpen(false)}>Chat about this</Link> : null}
      {onSeed ? <button type="button" className="poster-action-item" onClick={() => { onSeed(item); setOpen(false); }}>More like this</button> : null}
      {motifWhy ? <button type="button" className="poster-action-item" onClick={() => { flashStatus(motifWhy.summary || "This title matches the current context."); }}>Why this?</button> : null}
      <button type="button" className="poster-action-item" onClick={() => setReportOpen(true)}>Report issue…</button>
      {isOwner ? <div className="poster-action-owner">
        <span className="poster-action-label">Owner tools</span>
        {item?.rating_key || item?.plex_rating_key ? (
          <>
            <button type="button" className="poster-action-item" data-testid="poster-action-mark-bad-media" onClick={() => { setOpen(false); setBadMediaOpen(true); }}>
              Mark as bad media
            </button>
            <button type="button" className="poster-action-item" onClick={deleteIndex}>Delete from index</button>
          </>
        ) : null}
      </div> : null}
    </div>,
    document.body,
  ) : null;

  const flashToast = flash && typeof document !== "undefined" ? createPortal(
    <div className="menu-action-flash" role="status" aria-live="polite" data-testid="poster-action-flash">
      {flash}
    </div>,
    document.body,
  ) : null;

  return <div className="poster-action-menu" ref={rootRef}>
    <button type="button" className="poster-action-grip" aria-label={`Actions for ${item?.title || "title"}`} aria-expanded={open} onClick={(event) => { event.preventDefault(); event.stopPropagation(); setOpen((value: any) => !value); }}>
      <span aria-hidden="true">⋮</span>
    </button>
    {popover}
    {flashToast}
    <ReportMediaIssueModal item={item} open={reportOpen} onClose={() => setReportOpen(false)} onReported={() => flashStatus("Issue reported to the owner queue.")} />
    <MarkBadMediaDialog
      open={badMediaOpen}
      title={item?.title || "Untitled"}
      mediaType={item?.media_type || "movie"}
      loading={badMediaLoading}
      onCancel={() => setBadMediaOpen(false)}
      onConfirm={handleMarkBadMedia}
    />
    {modal}
  </div>;
}

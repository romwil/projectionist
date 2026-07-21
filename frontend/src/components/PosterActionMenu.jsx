import { useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { useAnchoredPopover } from "../hooks/useAnchoredPopover";
import {
  addCuratedListItem,
  addWatchlistPin,
  deleteLibraryItems,
  listCuratedLists,
  setLibraryItemWatched,
} from "../api/client";
import { useAuthGate } from "./UserMenu";
import ReportMediaIssueModal from "./ReportMediaIssueModal";
import { recommendLikeHref } from "../lib/backNav.js";
import { canWatchOnPlex, plexWatchUrl, titleDetailPath } from "../lib/titleLinks.js";
import { posterWatchAction, watchedStatePatch } from "../lib/posterWatchAction.js";

function placePosterMenu(anchor, menu) {
  const margin = 8;
  const above = anchor.top - margin - menu.height;
  const below = anchor.bottom + margin;
  const top = above >= margin || below + menu.height > window.innerHeight
    ? Math.max(margin, Math.min(above, window.innerHeight - menu.height - margin))
    : Math.min(below, window.innerHeight - menu.height - margin);
  const left = Math.max(margin, Math.min(anchor.left, window.innerWidth - menu.width - margin));
  return { top: `${top}px`, left: `${left}px` };
}

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
}) {
  const { isOwner, multiUserEnabled, role } = useAuthGate();
  const [lists, setLists] = useState([]);
  const [listOpen, setListOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [status, setStatus] = useState("");
  // Optimistic overlay so the menu label + card reflect a completed scrobble
  // without waiting on a parent refresh.
  const [watchPatch, setWatchPatch] = useState(null);
  const { open, setOpen, rootRef, popoverRef, popoverStyle } = useAnchoredPopover({
    closeOnEscape: true,
    anchorSelector: ".poster-action-grip",
    placement: placePosterMenu,
    repositionKey: `${listOpen}|${status}`,
  });
  const detailPath = titleDetailPath({ ...item, in_library: true });
  const plexHref = item?.plex_watch_url || (canWatchOnPlex(item) ? plexWatchUrl(item.rating_key) : "");
  const effectiveItem = watchPatch ? { ...item, ...watchPatch } : item;
  const watchAction = posterWatchAction(effectiveItem, { role, multiUserEnabled });

  async function openLists() {
    setListOpen(true);
    try {
      const payload = await listCuratedLists();
      setLists(payload?.items || payload || []);
    } catch (error) {
      setStatus(error.message || "Could not load lists.");
    }
  }

  async function addToList(list) {
    try {
      await addCuratedListItem(list.id, {
        tmdb_id: item?.tmdb_id || undefined,
        tvdb_id: item?.tvdb_id || undefined,
        media_type: item?.media_type,
        title: item?.title,
        library_item_id: item?.id && Number.isInteger(Number(item.id)) ? Number(item.id) : undefined,
      });
      setStatus(`Added to ${list.name || "list"}.`);
      setListOpen(false);
    } catch (error) {
      setStatus(error.message || "Could not add to list.");
    }
  }

  async function togglePin() {
    try {
      if (onTogglePin) await onTogglePin(item);
      else await addWatchlistPin({ tmdb_id: item?.tmdb_id, tvdb_id: item?.tvdb_id, media_type: item?.media_type, title: item?.title });
      setStatus(pinned ? "Removed from watchlist." : "Pinned to watchlist.");
    } catch (error) {
      setStatus(error.message || "Could not update watchlist.");
    }
  }

  async function toggleWatched() {
    if (!watchAction) return;
    const nextWatched = watchAction.nextWatched;
    try {
      const result = await setLibraryItemWatched(item.rating_key || item.plex_rating_key, nextWatched);
      const patch = watchedStatePatch(nextWatched);
      if (result && typeof result.view_count === "number") patch.view_count = result.view_count;
      setWatchPatch(patch);
      onWatchedChange?.(item, patch, result);
      const plexNote =
        result?.plex_synced === false
          ? result.plex_reason === "plex_not_configured"
            ? " (local only — Plex not configured)"
            : result.plex_reason === "plex_error"
              ? " (saved locally; Plex sync failed)"
              : " (local only)"
          : "";
      setStatus(nextWatched ? `Marked as watched${plexNote}.` : `Marked as unwatched${plexNote}.`);
    } catch (error) {
      setStatus(error.message || "Could not update watched state.");
    }
  }

  async function deleteIndex() {
    if (!window.confirm(`Remove "${item.title || "this title"}" from the CuratorX index? Plex files are not deleted.`)) return;
    try {
      await deleteLibraryItems([item.rating_key || item.plex_rating_key]);
      setStatus("Removed from the CuratorX index.");
    } catch (error) {
      setStatus(error.message || "Could not remove title.");
    }
  }

  const popover = open && typeof document !== "undefined" ? createPortal(
    <div className="poster-action-popover" ref={popoverRef} role="menu" style={popoverStyle || { visibility: "hidden" }}>
      {detailPath ? <Link to={detailPath} onClick={() => setOpen(false)}>Open details</Link> : null}
      {plexHref ? <a href={plexHref} target="_blank" rel="noopener noreferrer">Watch on Plex</a> : null}
      {watchAction ? <button type="button" className="poster-action-watched" onClick={toggleWatched}>{watchAction.label}</button> : null}
      <button type="button" onClick={togglePin}>{pinned ? "Remove from watchlist" : "Add to watchlist"}</button>
      {listId && onRemoveFromList ? <button type="button" onClick={async () => { await onRemoveFromList(listId, listItemId); onRemovedFromList?.(); }}>Remove from this collection</button> : null}
      <button type="button" onClick={openLists}>Add to list or playlist…</button>
      {listOpen ? <div className="poster-action-submenu">
        {lists.length ? lists.map((list) => <button key={list.id} type="button" onClick={() => addToList(list)}>{list.name} <span>{list.list_kind === "playlist" ? "Playlist" : "List"}</span></button>) : <span>No lists yet</span>}
      </div> : null}
      {onRecommend && multiUserEnabled ? <button type="button" onClick={() => { onRecommend(item); setOpen(false); }}>Recommend</button> : null}
      {item?.title ? <Link to={recommendLikeHref(item)} onClick={() => setOpen(false)}>Recommend like this in chat</Link> : null}
      {onSeed ? <button type="button" onClick={() => { onSeed(item); setOpen(false); }}>More like this</button> : null}
      {motifWhy ? <button type="button" onClick={() => { setStatus(motifWhy.summary || "This title matches the current context."); }}>Why this?</button> : null}
      <button type="button" onClick={() => setReportOpen(true)}>Report issue…</button>
      {isOwner ? <div className="poster-action-owner">
        <span>Owner tools</span>
        {item?.rating_key || item?.plex_rating_key ? <button type="button" onClick={deleteIndex}>Delete from index</button> : null}
      </div> : null}
      {status ? <p className="poster-action-status">{status}</p> : null}
    </div>,
    document.body,
  ) : null;

  return <div className="poster-action-menu" ref={rootRef}>
    <button type="button" className="poster-action-grip" aria-label={`Actions for ${item?.title || "title"}`} aria-expanded={open} onClick={(event) => { event.preventDefault(); event.stopPropagation(); setOpen((value) => !value); }}>
      <span aria-hidden="true">⋮</span>
    </button>
    {popover}
    <ReportMediaIssueModal item={item} open={reportOpen} onClose={() => setReportOpen(false)} onReported={() => setStatus("Issue reported to the owner queue.")} />
  </div>;
}

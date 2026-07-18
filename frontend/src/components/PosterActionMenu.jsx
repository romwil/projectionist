import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  addCuratedListItem,
  addWatchlistPin,
  deleteLibraryItems,
  listCuratedLists,
  setLibraryItemWatched,
} from "../api/client";
import { useAuthGate } from "./UserMenu";
import ReportMediaIssueModal from "./ReportMediaIssueModal";
import { canWatchOnPlex, plexWatchUrl, titleDetailPath } from "../lib/titleLinks.js";

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
  motifWhy,
}) {
  const { isOwner, multiUserEnabled } = useAuthGate();
  const [open, setOpen] = useState(false);
  const [lists, setLists] = useState([]);
  const [listOpen, setListOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [status, setStatus] = useState("");
  const rootRef = useRef(null);
  const detailPath = titleDetailPath({ ...item, in_library: true });
  const plexHref = item?.plex_watch_url || (canWatchOnPlex(item) ? plexWatchUrl(item.rating_key) : "");

  useEffect(() => {
    function close(event) {
      if (!rootRef.current?.contains(event.target)) setOpen(false);
    }
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

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

  async function markWatched() {
    try {
      await setLibraryItemWatched(item.rating_key || item.plex_rating_key, true);
      setStatus("Marked watched.");
    } catch (error) {
      setStatus(error.message || "Could not mark watched.");
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

  return <div className="poster-action-menu" ref={rootRef}>
    <button type="button" className="poster-action-grip" aria-label={`Actions for ${item?.title || "title"}`} aria-expanded={open} onClick={(event) => { event.preventDefault(); event.stopPropagation(); setOpen((value) => !value); }}>
      <span aria-hidden="true">⋮</span>
    </button>
    {open ? <div className="poster-action-popover" role="menu">
      {detailPath ? <Link to={detailPath} onClick={() => setOpen(false)}>Open details</Link> : null}
      {plexHref ? <a href={plexHref} target="_blank" rel="noopener noreferrer">Watch on Plex</a> : null}
      <button type="button" onClick={togglePin}>{pinned ? "Unpin watchlist" : "Pin to watchlist"}</button>
      {listId && onRemoveFromList ? <button type="button" onClick={async () => { await onRemoveFromList(listId, listItemId); onRemovedFromList?.(); }}>Remove from this playlist</button> : null}
      <button type="button" onClick={openLists}>Add to list or playlist…</button>
      {listOpen ? <div className="poster-action-submenu">
        {lists.length ? lists.map((list) => <button key={list.id} type="button" onClick={() => addToList(list)}>{list.name} <span>{list.list_kind === "playlist" ? "Playlist" : "List"}</span></button>) : <span>No lists yet</span>}
      </div> : null}
      {onRecommend && multiUserEnabled ? <button type="button" onClick={() => { onRecommend(item); setOpen(false); }}>Recommend</button> : null}
      {onSeed ? <button type="button" onClick={() => { onSeed(item); setOpen(false); }}>More like this</button> : null}
      {motifWhy ? <button type="button" onClick={() => { setStatus(motifWhy.summary || "This title matches the current context."); }}>Why this?</button> : null}
      <button type="button" onClick={() => setReportOpen(true)}>Report issue…</button>
      {isOwner ? <div className="poster-action-owner">
        <span>Owner tools</span>
        {item?.rating_key || item?.plex_rating_key ? <button type="button" onClick={markWatched}>Mark watched</button> : null}
        {item?.rating_key || item?.plex_rating_key ? <button type="button" onClick={deleteIndex}>Delete from index</button> : null}
      </div> : null}
      {status ? <p className="poster-action-status">{status}</p> : null}
    </div> : null}
    <ReportMediaIssueModal item={item} open={reportOpen} onClose={() => setReportOpen(false)} onReported={() => setStatus("Issue reported to the owner queue.")} />
  </div>;
}

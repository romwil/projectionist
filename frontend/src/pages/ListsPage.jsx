import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getCuratedList, listCuratedLists } from "../api/client";
import BackLink from "../components/BackLink";
import LibraryMediaCard from "../components/LibraryMediaCard";
import AppShell from "../layouts/AppShell";
import { ROUTES } from "../lib/browseLinks.js";

export default function ListsPage() {
  const { listId } = useParams();
  const [state, setState] = useState({ loading: true, lists: [], list: null, error: "" });
  useEffect(() => {
    let cancelled = false;
    const request = listId ? getCuratedList(listId) : listCuratedLists();
    request.then((data) => {
      if (cancelled) return;
      setState({ loading: false, lists: listId ? [] : data?.items || data || [], list: listId ? data : null, error: "" });
    }).catch((error) => !cancelled && setState({ loading: false, lists: [], list: null, error: error.message || "Could not load lists." }));
    return () => { cancelled = true; };
  }, [listId]);
  const items = state.list?.items || [];
  return <AppShell className="app-root lists-page" testId="lists-page" variant="browse" leading={<BackLink fallbackTo={ROUTES.explore} />}>
    <section className="explore-section-hero"><p className="person-eyebrow">{listId ? state.list?.list_kind || "List" : "Collections"}</p><h1>{listId ? state.list?.name || "List" : "Lists & playlists"}</h1><p className="explore-section-subtitle">Lists are intentional CuratorX shelves. Watchlist pins answer “keep this in mind”; playlists answer “play these together.”</p></section>
    {state.loading ? <p className="status status-secondary">Loading…</p> : null}
    {state.error ? <p className="error">{state.error}</p> : null}
    {!listId && !state.loading ? <div className="curated-list-grid">{state.lists.map((list) => <Link key={list.id} to={`/lists/${list.id}`} className="review-prompt-card"><strong>{list.name}</strong><span>{list.list_kind === "playlist" ? "Playlist" : "List"}</span></Link>)}</div> : null}
    {listId && items.length ? <div className="explore-poster-wall">{items.map((entry) => <LibraryMediaCard key={entry.id || entry.rating_key || entry.title} item={entry.media || entry} />)}</div> : null}
  </AppShell>;
}

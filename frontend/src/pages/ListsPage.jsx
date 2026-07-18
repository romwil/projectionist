import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { deleteCuratedListItem, getCuratedList, listCuratedLists } from "../api/client";
import BackLink from "../components/BackLink";
import MediaBrowseControls from "../components/MediaBrowseControls";
import MediaBrowseResults from "../components/MediaBrowseResults";
import RecommendModal from "../components/RecommendModal";
import { useAuthGate } from "../components/UserMenu";
import AppShell from "../layouts/AppShell";
import { ROUTES } from "../lib/browseLinks.js";
import { buildMediaBrowseParams, mediaBrowseRowsToCsv, parseMediaBrowse } from "../lib/mediaBrowse.js";

export default function ListsPage() {
  const { listId } = useParams();
  const { multiUserEnabled } = useAuthGate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [state, setState] = useState({ loading: true, lists: [], list: null, error: "" });
  const [columns, setColumns] = useState(null);
  const [recommendItem, setRecommendItem] = useState(null);
  const browse = useMemo(() => parseMediaBrowse(searchParams), [searchParams]);
  useEffect(() => {
    let cancelled = false;
    const request = listId ? getCuratedList(listId) : listCuratedLists();
    request.then((data) => {
      if (cancelled) return;
      setState({ loading: false, lists: listId ? [] : data?.items || data || [], list: listId ? data : null, error: "" });
    }).catch((error) => !cancelled && setState({ loading: false, lists: [], list: null, error: error.message || "Could not load lists." }));
    return () => { cancelled = true; };
  }, [listId]);
  const items = useMemo(() => {
    const source = (state.list?.items || [])
      .map((entry) => ({ ...(entry.media || entry), _listItemId: entry.id }))
      .filter((item) => !browse.media_type || item?.media_type === browse.media_type)
      .filter((item) => !browse.year || String(item?.year || "") === String(browse.year))
      .filter((item) => !browse.watch_state || (
        browse.watch_state === "watched" ? Boolean(item?.watched) :
          browse.watch_state === "in_progress" ? Boolean(item?.view_offset) :
            !item?.watched
      ));
    const direction = browse.sort_dir === "desc" ? -1 : 1;
    return [...source].sort((left, right) => {
      const a = left?.[browse.sort] ?? (browse.sort === "vote_average" ? left?.rating : "") ?? "";
      const b = right?.[browse.sort] ?? (browse.sort === "vote_average" ? right?.rating : "") ?? "";
      return String(a).localeCompare(String(b), undefined, { numeric: true }) * direction;
    });
  }, [browse.media_type, browse.sort, browse.sort_dir, browse.watch_state, browse.year, state.list?.items]);

  function handleBrowseChange(patch) {
    setSearchParams(buildMediaBrowseParams(browse, patch), { replace: true });
  }

  function exportCurrentPage(exportColumns) {
    const blob = new Blob([mediaBrowseRowsToCsv(items, exportColumns)], { type: "text/csv;charset=utf-8" });
    const href = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = href;
    link.download = `${state.list?.name || "collection"}.csv`;
    link.click();
    URL.revokeObjectURL(href);
  }

  async function removeFromCollection(collectionId, itemId) {
    await deleteCuratedListItem(collectionId, itemId);
    setState((current) => ({
      ...current,
      list: current.list
        ? {
          ...current.list,
          items: current.list.items.filter((entry) => String(entry.id) !== String(itemId)),
        }
        : current.list,
    }));
  }

  return <AppShell className="app-root lists-page" testId="lists-page" variant="browse" leading={<BackLink fallbackTo={ROUTES.explore} />}>
    <section className="explore-section-hero"><p className="person-eyebrow">{listId ? state.list?.list_kind || "List" : "Collections"}</p><h1>{listId ? state.list?.name || "List" : "Lists & playlists"}</h1><p className="explore-section-subtitle">Lists are intentional CuratorX shelves. Watchlist pins answer “keep this in mind”; playlists answer “play these together.”</p></section>
    {state.loading ? <p className="status status-secondary">Loading…</p> : null}
    {state.error ? <p className="error">{state.error}</p> : null}
    {!listId && !state.loading ? <div className="curated-list-grid">{state.lists.map((list) => <Link key={list.id} to={`/lists/${list.id}`} className="review-prompt-card"><strong>{list.name}</strong><span>{list.list_kind === "playlist" ? "Playlist" : "List"}</span></Link>)}</div> : null}
    {listId && !state.loading ? (
      <section className="tag-results">
        <MediaBrowseControls
          state={browse}
          onChange={handleBrowseChange}
          columns={columns}
          onColumnsChange={setColumns}
          columnScope={`list-${listId}`}
          exportItems
          onExport={exportCurrentPage}
        />
        {items.length ? (
          <MediaBrowseResults
            state={browse}
            items={items}
            columns={columns || undefined}
            cardProps={(item) => ({
              testId: "list-title-card",
              showRecommend: multiUserEnabled,
              onRecommend: multiUserEnabled ? setRecommendItem : undefined,
              listId,
              listItemId: item._listItemId,
              onRemoveFromList: removeFromCollection,
            })}
          />
        ) : <p className="explore-empty status status-secondary">This {state.list?.list_kind === "playlist" ? "playlist" : "list"} has no titles yet.</p>}
      </section>
    ) : null}
    <RecommendModal
      item={recommendItem}
      open={Boolean(recommendItem)}
      onClose={() => setRecommendItem(null)}
    />
  </AppShell>;
}

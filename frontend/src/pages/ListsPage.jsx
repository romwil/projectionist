import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { deleteCuratedListItem, getCuratedList, listCuratedLists } from "../api/client";
import BackLink from "../components/BackLink";
import CourseAuthoringPanel from "../components/CourseAuthoringPanel";
import MediaBrowseControls from "../components/MediaBrowseControls";
import MediaBrowsePagination from "../components/MediaBrowsePagination";
import MediaBrowseResults from "../components/MediaBrowseResults";
import RecommendModal from "../components/RecommendModal";
import { useAuthGate } from "../components/UserMenu";
import AppShell from "../layouts/AppShell";
import { ROUTES } from "../lib/browseLinks.js";
import { pageAgentListItems } from "../lib/agentResultLists.js";
import {
  MEDIA_BROWSE_PAGE_SIZES,
  buildMediaBrowseParams,
  isAllPageSize,
  matchesMediaBrowseWatchState,
  mediaBrowseRowsToCsv,
  parseMediaBrowse,
} from "../lib/mediaBrowse.js";

export default function ListsPage() {
  const { listId } = useParams();
  const { multiUserEnabled, isOwner } = useAuthGate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [state, setState] = useState({ loading: true, lists: [], list: null, error: "" });
  const [columns, setColumns] = useState(null);
  const [recommendItem, setRecommendItem] = useState(null);
  const browse = useMemo(() => parseMediaBrowse(searchParams), [searchParams]);
  const reload = useCallback(async () => {
    const data = listId ? await getCuratedList(listId) : await listCuratedLists();
    setState({
      loading: false,
      lists: listId ? [] : data?.items || data || [],
      list: listId ? data : null,
      error: "",
    });
  }, [listId]);
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
      .filter((item) => !browse.genres.length || browse.genres.every((genre) => (item?.genres || []).includes(genre)))
      .filter((item) => matchesMediaBrowseWatchState(item, browse.watch_state));
    const direction = browse.sort_dir === "desc" ? -1 : 1;
    return [...source].sort((left, right) => {
      const a = left?.[browse.sort] ?? (browse.sort === "vote_average" ? left?.rating : "") ?? "";
      const b = right?.[browse.sort] ?? (browse.sort === "vote_average" ? right?.rating : "") ?? "";
      return String(a).localeCompare(String(b), undefined, { numeric: true }) * direction;
    });
  }, [browse.genres, browse.media_type, browse.sort, browse.sort_dir, browse.watch_state, browse.year, state.list?.items]);
  const page = useMemo(
    () => pageAgentListItems(items, { limit: browse.limit, offset: browse.offset }),
    [browse.limit, browse.offset, items],
  );
  const filterOptions = useMemo(() => ({
    years: [...new Set(items.map((item) => item?.year).filter(Boolean))].sort((a, b) => b - a),
    genres: [...new Set(items.flatMap((item) => item?.genres || []).filter(Boolean))].sort(),
  }), [items]);
  const allPages = isAllPageSize(browse.limit);
  const pageSize = allPages ? Math.max(1, page.total) : Number(browse.limit) || 48;
  const pageNumber = allPages ? 1 : Math.floor(browse.offset / pageSize) + 1;
  const pageCount = allPages ? 1 : Math.max(1, Math.ceil(page.total / pageSize));
  const paginationSummary = allPages
    ? `${page.total} title${page.total === 1 ? "" : "s"}`
    : `Page ${pageNumber} of ${pageCount}${page.total ? ` · ${page.total} titles` : ""}`;

  function handleBrowseChange(patch) {
    setSearchParams(buildMediaBrowseParams(browse, patch), { replace: true });
  }

  function exportCurrentPage(exportColumns) {
    const blob = new Blob([mediaBrowseRowsToCsv(page.items, exportColumns)], { type: "text/csv;charset=utf-8" });
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
    <section className="explore-section-hero"><p className="person-eyebrow">{listId ? state.list?.list_kind || "List" : "Collections"}</p><h1>{listId ? state.list?.name || "List" : "Lists & playlists"}</h1><p className="explore-section-subtitle">Lists are intentional Projectionist shelves. Watchlist pins answer “keep this in mind”; playlists answer “play these together.”</p></section>
    {state.loading ? <p className="status status-secondary">Loading…</p> : null}
    {state.error ? <p className="error">{state.error}</p> : null}
    {!listId && !state.loading ? <div className="curated-list-grid">{state.lists.map((list) => <Link key={list.id} to={`/lists/${list.id}`} className="review-prompt-card"><strong>{list.name}</strong><span>{list.list_kind === "playlist" ? "Playlist" : "List"}</span></Link>)}</div> : null}
    {listId && !state.loading && isOwner ? (
      <CourseAuthoringPanel list={state.list} onRefresh={reload} />
    ) : null}
    {listId && !state.loading ? (
      <section className="tag-results">
        <MediaBrowseControls
          state={browse}
          onChange={handleBrowseChange}
          columns={columns}
          onColumnsChange={setColumns}
          columnScope={`list-${listId}`}
          filterOptions={filterOptions}
          pageSizes={MEDIA_BROWSE_PAGE_SIZES}
          exportItems
          onExport={exportCurrentPage}
        />
        <p className="explore-section-pagination-summary" data-testid="list-browse-summary">
          {paginationSummary}
        </p>
        {page.items.length ? (
          <MediaBrowseResults
            state={browse}
            items={page.items}
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
        ) : <p className="explore-empty status status-secondary">{page.total ? "No titles on this page." : `This ${state.list?.list_kind === "playlist" ? "playlist" : "list"} has no titles yet.`}</p>}
        {page.total ? (
          <MediaBrowsePagination
            summary={paginationSummary}
            pageSize={allPages ? "all" : pageSize}
            pageSizes={MEDIA_BROWSE_PAGE_SIZES}
            onPageSizeChange={(limit) => handleBrowseChange({ limit, offset: 0 })}
            hasPrevious={page.hasPrevious}
            hasNext={page.hasNext}
            onPrevious={() => handleBrowseChange({ offset: Math.max(0, browse.offset - pageSize) })}
            onNext={() => handleBrowseChange({ offset: browse.offset + pageSize })}
            testIdPrefix="list-browse"
          />
        ) : null}
      </section>
    ) : null}
    <RecommendModal
      item={recommendItem}
      open={Boolean(recommendItem)}
      onClose={() => setRecommendItem(null)}
    />
  </AppShell>;
}

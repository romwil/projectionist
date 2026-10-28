import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  addWatchlistPin,
  deleteLibraryItems,
  getExploreFeedRecentReleases,
  getExploreFeedRecentlyAdded,
} from "../api/client";
import BackLink from "../components/BackLink";
import BrowseResultsRegion from "../components/BrowseResultsRegion";
import { useBulkActionProgress } from "../components/BulkActionProgress";
import BulkLibraryDeleteDialog from "../components/BulkLibraryDeleteDialog";
import RemovalSummaryDialog from "../components/RemovalSummaryDialog";
import MediaBrowseControls from "../components/MediaBrowseControls";
import MediaBrowsePagination from "../components/MediaBrowsePagination";
import MediaBrowseResults from "../components/MediaBrowseResults";
import { useAuthGate } from "../components/UserMenu";
import { useRemovalProgressSession } from "../hooks/useRemovalProgressSession.js";
import AppShell from "../layouts/AppShell";
import { exploreSectionPath } from "../lib/browseLinks.js";
import { ROUTES } from "../lib/backNav.js";
import {
  BULK_DELETE_EMPTY_SELECTION_MESSAGE,
  formatBulkLibraryDeleteResultMessage,
  libraryBrowseItemKey,
  partitionBulkDeleteSelection,
} from "../lib/bulkLibraryDelete.js";
import {
  EXPLORE_PAGE_SIZES,
  buildExploreSectionQuery,
  exploreSectionSortOptions,
  feedPaginationSummary,
  getExploreSectionConfig,
  normalizeFeed,
  parseExploreSectionQuery,
  sortExploreSectionItems,
} from "../lib/exploreFeeds.js";
import { matchesMediaBrowseWatchState } from "../lib/mediaBrowse.js";
import { allowWatchlistPin } from "../lib/watchlistPin.js";

const FEED_LOADERS = {
  "recently-added": getExploreFeedRecentlyAdded,
  "recent-releases": getExploreFeedRecentReleases,
};

const MEDIA_TABS = [
  { id: "all", label: "All", mediaType: null },
  { id: "movie", label: "Movies", mediaType: "movie" },
  { id: "show", label: "TV", mediaType: "show" },
];

function matchesBrowseFilters(item: any, query: any) {
  if (query.year && String(item?.year || "") !== String(query.year)) return false;
  if (!matchesMediaBrowseWatchState(item, query.watch_state)) return false;
  if (query.genres?.length) {
    const itemGenres = (item?.genres || []).map((genre: any) => String(genre).toLowerCase());
    if (!query.genres.some((genre: any) => itemGenres.includes(String(genre).toLowerCase())))
      return false;
  }
  return true;
}

function csvCell(value: any) {
  const text = Array.isArray(value) ? value.join(" · ") : String(value ?? "");
  return `"${text.replaceAll('"', '""')}"`;
}

export default function ExploreSectionPage() {
  const { sectionId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { isOwner } = useAuthGate();
  const { start, update, finish } = useBulkActionProgress();
  const removal = useRemovalProgressSession();
  const config = getExploreSectionConfig(sectionId);
  const query = useMemo(() => parseExploreSectionQuery(searchParams), [searchParams]);
  const [state, setState] = useState<any>({
    loading: true,
    items: [] as any[],
    note: null,
    error: "",
    payload: null,
  });
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [actionStatus, setActionStatus] = useState("");
  const [pinning, setPinning] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [columns, setColumns] = useState<any | null>(null);

  useEffect(() => {
    if (!config) return undefined;
    const loader = (FEED_LOADERS as any)[config.feed];
    if (!loader) return undefined;
    let cancelled = false;
    setState((prev: any) => ({ ...prev, loading: true, error: "" }));
    setSelected(new Set());
    setActionStatus("");
    setDeleteOpen(false);
    setDeleteError("");
    loader({
      limit: query.limit,
      offset: query.offset,
      days: config.defaultDays,
      mediaType: query.mediaType,
    })
      .then((payload: any) => {
        if (cancelled) return;
        const normalized = normalizeFeed(payload);
        setState({
          loading: false,
          items: normalized.items,
          note: normalized.note,
          error: "",
          payload,
        });
      })
      .catch((err: any) => {
        if (cancelled) return;
        setState({
          loading: false,
          items: [],
          note: null,
          error: (err as { message?: string }).message || "Could not load this section.",
          payload: null,
        });
      });
    return () => {
      cancelled = true;
    };
  }, [config, query.limit, query.offset, query.mediaType]);

  const sortedItems = useMemo(
    () =>
      sortExploreSectionItems(
        state.items.filter((item: any) => matchesBrowseFilters(item, query)),
        query.sort,
        query.sort_dir,
      ),
    [state.items, query],
  );

  const filterOptions = useMemo(
    () => ({
      years: [...new Set(state.items.map((item: any) => item.year).filter(Boolean))].sort(
        (a, b) => (b as any) - (a as any),
      ),
      genres: [...new Set(state.items.flatMap((item: any) => item.genres || []).filter(Boolean))].sort(),
    }),
    [state.items],
  );

  const summary = useMemo(
    () => feedPaginationSummary(state.payload || { items: state.items, total: state.items.length }),
    [state.items, state.payload],
  );

  const pinnableKeys = useMemo(
    () => new Set(sortedItems.filter(allowWatchlistPin).map(libraryBrowseItemKey)),
    [sortedItems],
  );

  const deletePartition = useMemo(
    () => partitionBulkDeleteSelection(sortedItems, selected, libraryBrowseItemKey),
    [sortedItems, selected],
  );

  function updateQuery(updates: any) {
    const params = buildExploreSectionQuery(query, updates);
    setSearchParams(params, { replace: true });
  }

  function handleMediaTab(mediaType: any) {
    updateQuery({ mediaType, offset: 0 });
  }

  function handlePageChange(page: any) {
    const nextOffset = Math.max(0, (page - 1) * query.limit);
    updateQuery({ offset: nextOffset });
  }

  function handlePageSizeChange(limit: any) {
    updateQuery({ limit, offset: 0 });
  }

  function handleBrowseChange(patch: any) {
    const updates = { ...patch };
    if (Object.hasOwn(patch, "media_type")) {
      updates.mediaType = patch.media_type || null;
      delete updates.media_type;
    }
    updateQuery(updates);
  }

  function exportCurrentPage(columns: any) {
    const header = columns.join(",");
    const rows = sortedItems.map((item) =>
      columns.map((column: any) => csvCell(item?.[column])).join(","),
    );
    const blob = new Blob([[header, ...rows].join("\n")], { type: "text/csv;charset=utf-8" });
    const href = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = href;
    link.download = `${config.id}-${query.offset + 1}-${query.offset + sortedItems.length}.csv`;
    link.click();
    URL.revokeObjectURL(href);
  }

  function toggleSelect(item: any) {
    if (deleteOpen || deleting) return;
    const key = libraryBrowseItemKey(item);
    if (!pinnableKeys.has(key)) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function selectAllOnPage() {
    if (deleteOpen || deleting) return;
    setSelected(new Set(pinnableKeys));
  }

  function clearSelection() {
    if (deleteOpen || deleting) return;
    setSelected(new Set());
  }

  async function handleBulkPin() {
    if (!selected.size || pinning) return;
    const targets = sortedItems.filter(
      (item) => selected.has(libraryBrowseItemKey(item)) && allowWatchlistPin(item),
    );
    if (!targets.length) return;
    const progressId = start({
      label: "Pinning to watchlist",
      total: targets.length,
      asynchronous: true,
    });
    setPinning(true);
    setActionStatus("");
    let ok = 0;
    let failed = 0;
    for (const item of targets) {
      try {
        await addWatchlistPin({
          tmdb_id: item.tmdb_id || undefined,
          tvdb_id: item.tvdb_id || undefined,
          media_type: item.media_type,
          title: item.title || "Untitled",
        });
        ok += 1;
      } catch {
        failed += 1;
      } finally {
        update(progressId, ok + failed);
      }
    }
    setPinning(false);
    const summary = failed
      ? `Pinned ${ok}; ${failed} failed.`
      : `Pinned ${ok} title${ok === 1 ? "" : "s"} to watchlist.`;
    setActionStatus(summary);
    finish(progressId, { label: summary, state: failed ? "error" : "success" });
    setSelected(new Set());
  }

  function openBulkDelete() {
    if (!isOwner || !selected.size) return;
    setDeleteError("");
    setDeleteOpen(true);
  }

  async function handleBulkDeleteConfirm({ mode }: any = {}) {
    if (!isOwner || deleting) return;
    const { ratingKeys, titles } = deletePartition;
    if (!ratingKeys.length) {
      setDeleteError(BULK_DELETE_EMPTY_SELECTION_MESSAGE);
      return;
    }
    setDeleteOpen(false);
    setDeleting(true);
    setDeleteError("");
    const targets = ratingKeys.map((rating_key, index) => ({
      rating_key,
      title: titles[index],
    }));
    try {
      const result = await removal.run({
        mode,
        targets,
        stream: (opts: any) => deleteLibraryItems(ratingKeys, { mode, ...opts }),
      });
      const deletedCount = Number(result?.deleted) || 0;
      const errors = Array.isArray(result?.errors) ? result.errors : [];
      const okKeys = new Set(
        (Array.isArray(result?.results) ? result.results : [])
          .filter((entry: any) => entry?.index_deleted)
          .map((entry: any) => String(entry.rating_key || "").trim())
          .filter(Boolean),
      );
      const drop = okKeys.size ? okKeys : mode === "full" ? okKeys : new Set(ratingKeys);
      if (drop.size) {
        setState((prev: any) => {
          const nextItems = prev.items.filter((item: any) => {
            const key = String(item?.rating_key || item?.plex_rating_key || "").trim();
            return !key || !drop.has(key);
          });
          const prevTotal = Number(prev.payload?.total);
          const nextTotal = Number.isFinite(prevTotal)
            ? Math.max(0, prevTotal - deletedCount)
            : nextItems.length;
          return {
            ...prev,
            items: nextItems,
            payload: prev.payload
              ? { ...prev.payload, items: nextItems, total: nextTotal }
              : prev.payload,
          };
        });
        setSelected(new Set());
      }
      setActionStatus(formatBulkLibraryDeleteResultMessage(result, { titles: titles as any }));
      if (errors.length && !deletedCount) return;
    } catch (err: any) {
      setActionStatus((err as { message?: string }).message || "Could not delete selected titles.");
    } finally {
      setDeleting(false);
    }
  }

  if (!config) {
    return (
      <AppShell
        className="app-root explore-section-page"
        testId="explore-section-page"
        variant="browse"
        leading={<BackLink fallbackTo={ROUTES.explore} testId="explore-section-back" />}
      >
        <p className="error" data-testid="explore-section-unknown">
          Unknown Explore section.
        </p>
        <Link to={ROUTES.explore} className="app-topbar-link">
          Return to Explore
        </Link>
      </AppShell>
    );
  }

  const activeTab = MEDIA_TABS.find((tab) => tab.mediaType === query.mediaType)?.id || "all";
  const showToolbarPagination = Boolean(summary.total || summary.returned);

  return (
    <AppShell
      className="app-root explore-section-page"
      testId="explore-section-page"
      variant="browse"
      leading={<BackLink fallbackTo={ROUTES.explore} testId="explore-section-back" />}
      actions={
        <Link
          to={ROUTES.explore}
          className="app-topbar-link"
          data-testid="explore-section-hub-link"
        >
          Explore hub
        </Link>
      }
    >
      <section className="explore-section-hero" data-testid="explore-section-hero">
        <p className="person-eyebrow">Explore</p>
        <h1 data-testid="explore-section-title">{config.title}</h1>
        <p className="explore-section-subtitle">{config.subtitle}</p>
      </section>

      {config.supportsMediaType ? (
        <div
          className="explore-media-tabs"
          role="tablist"
          aria-label="Media type"
          data-testid="explore-section-media-tabs"
        >
          {MEDIA_TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.id}
              className={`explore-media-tab${activeTab === tab.id ? " is-active" : ""}`}
              data-testid={`explore-section-tab-${tab.id}`}
              onClick={() => handleMediaTab(tab.mediaType)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      ) : null}

      <div className="explore-section-toolbar" data-testid="explore-section-toolbar">
        <MediaBrowseControls
          state={{ ...query, media_type: query.mediaType || "" }}
          onChange={handleBrowseChange}
          columns={columns}
          onColumnsChange={setColumns}
          columnScope={`explore-${config.id}`}
          filterOptions={filterOptions}
          sortOptions={exploreSectionSortOptions(config.id)}
          pageSizes={EXPLORE_PAGE_SIZES}
          exportItems
          onExport={exportCurrentPage}
        />
        <div className="explore-section-toolbar-row">
          <div className="explore-section-toolbar-primary">
            {showToolbarPagination ? (
              <p
                className="explore-section-pagination-summary"
                data-testid="explore-section-page-summary"
              >
                Page {summary.page} of {summary.pageCount}
                {summary.total ? ` · ${summary.total} titles` : ""}
              </p>
            ) : null}
            {selected.size ? (
              <p
                className="explore-section-selection-summary"
                data-testid="explore-section-selection-summary"
              >
                {selected.size} selected
                {isOwner && deletePartition.unavailable.length
                  ? ` · ${deletePartition.unavailable.length} not deletable`
                  : ""}
              </p>
            ) : null}
          </div>
          <div className="explore-section-bulk" data-testid="explore-section-bulk">
            <button
              type="button"
              className="ghost"
              data-testid="explore-section-select-all"
              disabled={!pinnableKeys.size || deleteOpen || deleting}
              onClick={selectAllOnPage}
            >
              Select page
            </button>
            <button
              type="button"
              className="ghost"
              data-testid="explore-section-clear-selection"
              disabled={!selected.size || deleteOpen || deleting}
              onClick={clearSelection}
            >
              Clear
            </button>
            <button
              type="button"
              className="ghost"
              data-testid="explore-section-bulk-pin"
              disabled={!selected.size || pinning}
              onClick={handleBulkPin}
            >
              {pinning ? "Pinning…" : `Pin ${selected.size || ""} to watchlist`.trim()}
            </button>
            {isOwner ? (
              <button
                type="button"
                className="btn-danger"
                data-testid="explore-section-bulk-delete"
                disabled={!selected.size || !deletePartition.ratingKeys.length || deleting}
                onClick={openBulkDelete}
              >
                Delete
              </button>
            ) : null}
          </div>
        </div>
      </div>
      {actionStatus ? (
        <p
          className="status status-secondary explore-section-action-status"
          data-testid="explore-section-pin-status"
        >
          {actionStatus}
        </p>
      ) : null}

      <BrowseResultsRegion
        testId="explore-section-results"
        loading={state.loading}
        error={state.error}
        hasItems={sortedItems.length > 0}
        empty={
          <p className="explore-empty status status-secondary" data-testid="explore-section-empty">
            {state.note || "No titles in this section yet."}
          </p>
        }
      >
        <MediaBrowseResults
          state={{ ...query, media_type: query.mediaType || "" }}
          items={sortedItems}
          columns={columns || undefined}
          selectable
          selected={selected}
          onToggleSelect={toggleSelect}
          getItemKey={libraryBrowseItemKey}
        />
      </BrowseResultsRegion>

      {showToolbarPagination ? (
        <MediaBrowsePagination
          summary={`Page ${summary.page} of ${summary.pageCount}${
            summary.total ? ` · ${summary.total} titles` : ""
          }`}
          pageSize={query.limit}
          pageSizes={EXPLORE_PAGE_SIZES}
          onPageSizeChange={handlePageSizeChange}
          hasPrevious={summary.hasPrev}
          hasNext={summary.hasMore}
          onPrevious={() => handlePageChange(summary.page - 1)}
          onNext={() => handlePageChange(summary.page + 1)}
          testIdPrefix="explore-section"
          testIdSuffix="-footer"
        />
      ) : null}

      {query.mediaType ? (
        <p className="explore-section-footer-links">
          <button
            type="button"
            className="ghost"
            data-testid="explore-section-view-all-types"
            onClick={() => navigate((exploreSectionPath as any)(config.id))}
          >
            View all types
          </button>
        </p>
      ) : null}

      <RemovalSummaryDialog
        open={Boolean(removal.summary)}
        result={removal.summary}
        cancelRequested={removal.cancelRequested}
        onCancelRemaining={removal.cancelRemaining}
        onClose={removal.dismiss}
      />

      <BulkLibraryDeleteDialog
        open={deleteOpen}
        titles={deletePartition.titles}
        unavailableCount={deletePartition.unavailable.length}
        loading={deleting}
        error={deleteError}
        onCancel={() => {
          if (deleting) return;
          setDeleteOpen(false);
          setDeleteError("");
        }}
        onConfirm={handleBulkDeleteConfirm}
      />
    </AppShell>
  );
}

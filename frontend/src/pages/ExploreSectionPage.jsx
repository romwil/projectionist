import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  addWatchlistPin,
  deleteLibraryItems,
  getExploreFeedRecentReleases,
  getExploreFeedRecentlyAdded,
} from "../api/client";
import BackLink from "../components/BackLink.jsx";
import BulkLibraryDeleteDialog from "../components/BulkLibraryDeleteDialog.jsx";
import MediaBrowseControls from "../components/MediaBrowseControls.jsx";
import MediaBrowseResults from "../components/MediaBrowseResults.jsx";
import { useAuthGate } from "../components/UserMenu";
import AppShell from "../layouts/AppShell";
import { exploreSectionPath } from "../lib/browseLinks.js";
import { ROUTES } from "../lib/backNav.js";
import { partitionBulkDeleteSelection } from "../lib/bulkLibraryDelete.js";
import {
  EXPLORE_PAGE_SIZES,
  EXPLORE_SECTION_SORTS,
  buildExploreSectionQuery,
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

function itemKey(item) {
  return `${item?.media_type || ""}:${item?.tmdb_id || item?.rating_key || item?.title || ""}`;
}

function matchesBrowseFilters(item, query) {
  if (query.year && String(item?.year || "") !== String(query.year)) return false;
  if (!matchesMediaBrowseWatchState(item, query.watch_state)) return false;
  if (query.genres?.length) {
    const itemGenres = (item?.genres || []).map((genre) => String(genre).toLowerCase());
    if (!query.genres.some((genre) => itemGenres.includes(String(genre).toLowerCase()))) return false;
  }
  return true;
}

function csvCell(value) {
  const text = Array.isArray(value) ? value.join(" · ") : String(value ?? "");
  return `"${text.replaceAll("\"", "\"\"")}"`;
}

function SectionPagination({ summary, onPageChange, onPageSizeChange, pageSize, compact = false }) {
  if (!summary.total && !summary.returned) return null;
  const suffix = compact ? "-footer" : "";
  return (
    <div
      className={`explore-section-pagination${compact ? " is-compact" : ""}`}
      data-testid={`explore-section-pagination${suffix}`}
    >
      <p
        className="explore-section-pagination-summary"
        data-testid={`explore-section-page-summary${suffix}`}
      >
        Page {summary.page} of {summary.pageCount}
        {summary.total ? ` · ${summary.total} titles` : ""}
      </p>
      <div className="explore-section-pagination-controls">
        {compact ? null : (
          <label className="explore-section-page-size">
            <span>Per page</span>
            <select
              value={pageSize}
              data-testid="explore-section-page-size"
              onChange={(event) => onPageSizeChange(Number(event.target.value))}
            >
              {EXPLORE_PAGE_SIZES.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="explore-section-page-nav">
          <button
            type="button"
            className="ghost"
            data-testid={`explore-section-prev${suffix}`}
            disabled={!summary.hasPrev}
            onClick={() => onPageChange(summary.page - 1)}
          >
            Previous
          </button>
          <button
            type="button"
            className="ghost"
            data-testid={`explore-section-next${suffix}`}
            disabled={!summary.hasMore}
            onClick={() => onPageChange(summary.page + 1)}
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ExploreSectionPage() {
  const { sectionId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { isOwner } = useAuthGate();
  const config = getExploreSectionConfig(sectionId);
  const query = useMemo(() => parseExploreSectionQuery(searchParams), [searchParams]);
  const [state, setState] = useState({
    loading: true,
    items: [],
    note: null,
    error: "",
    payload: null,
  });
  const [selected, setSelected] = useState(() => new Set());
  const [actionStatus, setActionStatus] = useState("");
  const [pinning, setPinning] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [columns, setColumns] = useState(null);

  useEffect(() => {
    if (!config) return undefined;
    const loader = FEED_LOADERS[config.feed];
    if (!loader) return undefined;
    let cancelled = false;
    setState((prev) => ({ ...prev, loading: true, error: "" }));
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
      .then((payload) => {
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
      .catch((err) => {
        if (cancelled) return;
        setState({
          loading: false,
          items: [],
          note: null,
          error: err.message || "Could not load this section.",
          payload: null,
        });
      });
    return () => {
      cancelled = true;
    };
  }, [config, query.limit, query.offset, query.mediaType]);

  const sortedItems = useMemo(
    () => sortExploreSectionItems(
      state.items.filter((item) => matchesBrowseFilters(item, query)),
      query.sort,
      query.sort_dir,
    ),
    [state.items, query],
  );

  const filterOptions = useMemo(() => ({
    years: [...new Set(state.items.map((item) => item.year).filter(Boolean))].sort((a, b) => b - a),
    genres: [...new Set(state.items.flatMap((item) => item.genres || []).filter(Boolean))].sort(),
  }), [state.items]);

  const summary = useMemo(
    () => feedPaginationSummary(state.payload || { items: state.items, total: state.items.length }),
    [state.items, state.payload],
  );

  const pinnableKeys = useMemo(
    () => new Set(sortedItems.filter(allowWatchlistPin).map(itemKey)),
    [sortedItems],
  );

  const deletePartition = useMemo(
    () => partitionBulkDeleteSelection(sortedItems, selected, itemKey),
    [sortedItems, selected],
  );

  function updateQuery(updates) {
    const params = buildExploreSectionQuery(query, updates);
    setSearchParams(params, { replace: true });
  }

  function handleMediaTab(mediaType) {
    updateQuery({ mediaType, offset: 0 });
  }

  function handlePageChange(page) {
    const nextOffset = Math.max(0, (page - 1) * query.limit);
    updateQuery({ offset: nextOffset });
  }

  function handlePageSizeChange(limit) {
    updateQuery({ limit, offset: 0 });
  }

  function handleBrowseChange(patch) {
    const updates = { ...patch };
    if (Object.hasOwn(patch, "media_type")) {
      updates.mediaType = patch.media_type || null;
      delete updates.media_type;
    }
    updateQuery(updates);
  }

  function exportCurrentPage(columns) {
    const header = columns.join(",");
    const rows = sortedItems.map((item) => columns.map((column) => csvCell(item?.[column])).join(","));
    const blob = new Blob([[header, ...rows].join("\n")], { type: "text/csv;charset=utf-8" });
    const href = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = href;
    link.download = `${config.id}-${query.offset + 1}-${query.offset + sortedItems.length}.csv`;
    link.click();
    URL.revokeObjectURL(href);
  }

  function toggleSelect(item) {
    const key = itemKey(item);
    if (!pinnableKeys.has(key)) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function selectAllOnPage() {
    setSelected(new Set(pinnableKeys));
  }

  function clearSelection() {
    setSelected(new Set());
  }

  async function handleBulkPin() {
    if (!selected.size || pinning) return;
    const targets = sortedItems.filter((item) => selected.has(itemKey(item)) && allowWatchlistPin(item));
    if (!targets.length) return;
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
      }
    }
    setPinning(false);
    setActionStatus(
      failed
        ? `Pinned ${ok}; ${failed} failed.`
        : `Pinned ${ok} title${ok === 1 ? "" : "s"} to watchlist.`,
    );
    setSelected(new Set());
  }

  function openBulkDelete() {
    if (!isOwner || !selected.size) return;
    setDeleteError("");
    setDeleteOpen(true);
  }

  async function handleBulkDeleteConfirm() {
    if (!isOwner || deleting) return;
    const { ratingKeys, titles } = deletePartition;
    if (!ratingKeys.length) return;
    setDeleting(true);
    setDeleteError("");
    try {
      const result = await deleteLibraryItems(ratingKeys);
      const deletedCount = Number(result?.deleted) || 0;
      const drop = new Set(ratingKeys);
      setState((prev) => {
        const nextItems = prev.items.filter((item) => {
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
          payload: prev.payload ? { ...prev.payload, items: nextItems, total: nextTotal } : prev.payload,
        };
      });
      setSelected(new Set());
      setDeleteOpen(false);
      setActionStatus(
        deletedCount
          ? `Removed ${deletedCount} title${deletedCount === 1 ? "" : "s"} from the CuratorX library index.`
          : `No matching library records for ${titles.length} selected title${titles.length === 1 ? "" : "s"}.`,
      );
    } catch (err) {
      setDeleteError(err.message || "Could not delete selected titles.");
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

  const activeTab =
    MEDIA_TABS.find((tab) => tab.mediaType === query.mediaType)?.id || "all";
  const showToolbarPagination = Boolean(summary.total || summary.returned);

  return (
    <AppShell
      className="app-root explore-section-page"
      testId="explore-section-page"
      variant="browse"
      leading={<BackLink fallbackTo={ROUTES.explore} testId="explore-section-back" />}
      actions={
        <Link to={ROUTES.explore} className="app-topbar-link" data-testid="explore-section-hub-link">
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
          sortOptions={EXPLORE_SECTION_SORTS}
          exportItems
          onExport={exportCurrentPage}
        />
        <div className="explore-section-toolbar-row">
          <div className="explore-section-toolbar-primary">
            {showToolbarPagination ? (
              <label className="explore-section-page-size">
                <span>Per page</span>
                <select
                  value={query.limit}
                  data-testid="explore-section-page-size"
                  onChange={(event) => handlePageSizeChange(Number(event.target.value))}
                >
                  {EXPLORE_PAGE_SIZES.map((size) => (
                    <option key={size} value={size}>
                      {size}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            {selected.size ? (
              <p className="explore-section-selection-summary" data-testid="explore-section-selection-summary">
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
              disabled={!pinnableKeys.size}
              onClick={selectAllOnPage}
            >
              Select page
            </button>
            <button
              type="button"
              className="ghost"
              data-testid="explore-section-clear-selection"
              disabled={!selected.size}
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
        {showToolbarPagination ? (
          <div className="explore-section-toolbar-row explore-section-toolbar-nav">
            <p className="explore-section-pagination-summary" data-testid="explore-section-page-summary">
              Page {summary.page} of {summary.pageCount}
              {summary.total ? ` · ${summary.total} titles` : ""}
            </p>
            <div className="explore-section-page-nav">
              <button
                type="button"
                className="ghost"
                data-testid="explore-section-prev"
                disabled={!summary.hasPrev}
                onClick={() => handlePageChange(summary.page - 1)}
              >
                Previous
              </button>
              <button
                type="button"
                className="ghost"
                data-testid="explore-section-next"
                disabled={!summary.hasMore}
                onClick={() => handlePageChange(summary.page + 1)}
              >
                Next
              </button>
            </div>
          </div>
        ) : null}
      </div>
      {actionStatus ? (
        <p className="status status-secondary explore-section-action-status" data-testid="explore-section-pin-status">
          {actionStatus}
        </p>
      ) : null}

      <section className="explore-section-results" data-testid="explore-section-results">
        {state.loading ? <p className="status status-secondary">Loading…</p> : null}
        {state.error ? <p className="error">{state.error}</p> : null}
        {!state.loading && !state.error && !sortedItems.length ? (
          <p className="explore-empty status status-secondary" data-testid="explore-section-empty">
            {state.note || "No titles in this section yet."}
          </p>
        ) : null}
        {sortedItems.length ? (
          <MediaBrowseResults
            state={{ ...query, media_type: query.mediaType || "" }}
            items={sortedItems}
            columns={columns || undefined}
            selectable
            selected={selected}
            onToggleSelect={toggleSelect}
            getItemKey={itemKey}
          />
        ) : null}
      </section>

      <SectionPagination
        summary={summary}
        pageSize={query.limit}
        onPageChange={handlePageChange}
        onPageSizeChange={handlePageSizeChange}
        compact
      />

      {query.mediaType ? (
        <p className="explore-section-footer-links">
          <button
            type="button"
            className="ghost"
            data-testid="explore-section-view-all-types"
            onClick={() => navigate(exploreSectionPath(config.id))}
          >
            View all types
          </button>
        </p>
      ) : null}

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

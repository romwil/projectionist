import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  addWatchlistPin,
  deleteLibraryItems,
  getLibraryAggregate,
  queryLibrary,
} from "../api/client";
import BackLink from "../components/BackLink";
import { useBulkActionProgress } from "../components/BulkActionProgress";
import BulkLibraryDeleteDialog from "../components/BulkLibraryDeleteDialog";
import RemovalSummaryDialog from "../components/RemovalSummaryDialog";
import MediaBrowseControls from "../components/MediaBrowseControls";
import MediaBrowsePagination from "../components/MediaBrowsePagination";
import MediaBrowseResults from "../components/MediaBrowseResults";
import { useAuthGate } from "../components/UserMenu";
import { useRemovalProgressSession } from "../hooks/useRemovalProgressSession.js";
import AppShell from "../layouts/AppShell";
import { ROUTES } from "../lib/backNav.js";
import {
  BULK_DELETE_EMPTY_SELECTION_MESSAGE,
  formatBulkLibraryDeleteResultMessage,
  libraryBrowseItemKey,
  partitionBulkDeleteSelection,
} from "../lib/bulkLibraryDelete.js";
import { formatLanguageName } from "../lib/languageNames.js";
import {
  ALL_LANGUAGES_HEADING,
  ALL_LANGUAGES_LEDE,
  LANGUAGE_LANDING_LEDE,
  NO_MATCHING_TITLES,
  buildLanguageLandingSearch,
  languageLandingRequest,
  languageOptionsFromBuckets,
} from "../lib/languageLanding.js";
import {
  MEDIA_BROWSE_PAGE_SIZES,
  MEDIA_BROWSE_SORTS,
  MEDIA_BROWSE_TV_SORTS,
  isAllPageSize,
  mediaBrowseRowsToCsv,
  parseMediaBrowse,
} from "../lib/mediaBrowse.js";
import { allowWatchlistPin } from "../lib/watchlistPin.js";
import type { JsParam } from "../api/types";

const EMPTY_STATE = {
  loading: false,
  items: [] as JsParam[],
  total: 0,
  returned: 0,
  hasMore: false,
  offset: 0,
  error: "",
  note: "",
  queryKey: "",
};

export default function LanguageLandingPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { isOwner } = useAuthGate();
  const { start, update, finish } = useBulkActionProgress();
  const removal = useRemovalProgressSession();
  const rawLanguage = searchParams.get("language");
  const browse = useMemo(() => parseMediaBrowse(searchParams), [searchParams]);
  const request = useMemo(
    () => languageLandingRequest(rawLanguage, browse),
    [rawLanguage, browse],
  );
  const queryKey =
    request.kind === "query" ? JSON.stringify(request.filters) : request.kind;
  const [state, setState] = useState(EMPTY_STATE);
  const [seenKey, setSeenKey] = useState(queryKey);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [actionStatus, setActionStatus] = useState("");
  const [pinning, setPinning] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [columns, setColumns] = useState<any | null>(null);
  const [filterOptions, setFilterOptions] = useState<any>({ years: [] as any[], genres: [] as any[], languages: [] as any[] });

  useEffect(() => {
    let cancelled = false;
    const mediaType =
      browse.media_type === "movie" || browse.media_type === "show" ? browse.media_type : "";
    const aggregateOptions = mediaType ? { mediaType } : {};
    Promise.all([
      getLibraryAggregate("year", aggregateOptions).catch(() => ({ buckets: [] })),
      getLibraryAggregate("genre", aggregateOptions).catch(() => ({ buckets: [] })),
      getLibraryAggregate("language", aggregateOptions).catch(() => ({ buckets: [] })),
    ]).then(([yearAgg, genreAgg, languageAgg]) => {
      if (cancelled) return;
      setFilterOptions({
        years: [
          ...new Set((yearAgg?.buckets || []).map((bucket: any) => bucket.year).filter(Boolean)),
        ].sort((a, b) => (b as any) - (a as any)),
        genres: [
          ...new Set((genreAgg?.buckets || []).map((bucket: any) => bucket.genre).filter(Boolean)),
        ].sort(),
        languages: languageOptionsFromBuckets(languageAgg?.buckets),
      });
    });
    return () => {
      cancelled = true;
    };
  }, [browse.media_type, rawLanguage]);

  if (seenKey !== queryKey) {
    setSeenKey(queryKey);
    setSelected(new Set());
    setActionStatus("");
    setDeleteOpen(false);
    setDeleteError("");
  }

  useEffect(() => {
    if (request.kind !== "query") return undefined;
    let cancelled = false;
    const keyAtStart = queryKey;
    queryLibrary(request.filters)
      .then((data) => {
        if (cancelled) return;
        const items = Array.isArray(data?.items) ? data.items : [];
        setState({
          loading: false,
          items,
          total: Number(data?.total_matched ?? items.length) || 0,
          returned: Number(data?.returned ?? items.length) || items.length,
          hasMore: Boolean(data?.has_more),
          offset: Number(data?.offset ?? browse.offset) || 0,
          error: "",
          note: items.length ? "" : NO_MATCHING_TITLES,
          queryKey: keyAtStart,
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setState({
          ...EMPTY_STATE,
          error: (err as { message?: string }).message || "Could not load titles.",
          queryKey: keyAtStart,
        });
      });
    return () => {
      cancelled = true;
    };
  }, [request, queryKey, browse.offset]);

  const view =
    request.kind !== "query"
      ? { ...EMPTY_STATE, note: (request as any).message || NO_MATCHING_TITLES }
      : state.queryKey === queryKey
        ? state
        : { ...EMPTY_STATE, loading: true };

  const pinnableKeys = useMemo(
    () => new Set(view.items.filter(allowWatchlistPin).map(libraryBrowseItemKey)),
    [view.items],
  );
  const deletePartition = useMemo(
    () => partitionBulkDeleteSelection(view.items, selected, libraryBrowseItemKey),
    [view.items, selected],
  );

  const isAll = isAllPageSize(browse.limit);
  const pageSize = isAll ? view.returned || 1 : Number(browse.limit) || 48;
  const page = isAll ? 1 : Math.floor((view.offset || 0) / pageSize) + 1;
  const pageCount = isAll ? 1 : Math.max(1, Math.ceil((view.total || 0) / pageSize));
  const capped = isAll && view.total > view.returned;
  const paginationSummary = isAll
    ? capped
      ? `Showing first ${view.returned} of ${view.total} titles`
      : `${view.total} title${view.total === 1 ? "" : "s"}`
    : `Page ${page} of ${pageCount}${view.total ? ` · ${view.total} titles` : ""}`;
  const showToolbarPagination = Boolean(view.total || view.returned);
  const sortOptions = browse.media_type === "show" ? MEDIA_BROWSE_TV_SORTS : MEDIA_BROWSE_SORTS;
  const heading = request.code ? formatLanguageName(request.code) : ALL_LANGUAGES_HEADING;
  const lede = request.code ? LANGUAGE_LANDING_LEDE : ALL_LANGUAGES_LEDE;

  function updateSearch(updates: any) {
    setSearchParams(buildLanguageLandingSearch(rawLanguage, browse, updates), { replace: true });
  }

  function exportCurrentPage(exportColumns: any) {
    const blob = new Blob([mediaBrowseRowsToCsv(view.items, exportColumns)], {
      type: "text/csv;charset=utf-8",
    });
    const href = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = href;
    link.download = `language-${request.code || "titles"}.csv`;
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
    const targets = view.items.filter(
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
          tmdb_id: (item as any).tmdb_id || undefined,
          tvdb_id: (item as any).tvdb_id || undefined,
          media_type: (item as any).media_type,
          title: (item as any).title || "Untitled",
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
        setState((prev) => {
          const nextItems = prev.items.filter((item) => {
            const key = String((item as any)?.rating_key || (item as any)?.plex_rating_key || "").trim();
            return !key || !drop.has(key);
          });
          return {
            ...prev,
            items: nextItems,
            total: Math.max(0, (Number(prev.total) || 0) - deletedCount),
            returned: nextItems.length,
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

  return (
    <AppShell
      className="app-root explore-section-page"
      testId="language-landing-page"
      variant="browse"
      leading={<BackLink fallbackTo={ROUTES.explore} testId="language-landing-back" />}
      actions={
        <Link to={ROUTES.explore} className="app-topbar-link" data-testid="language-landing-hub-link">
          Explore hub
        </Link>
      }
    >
      <section className="explore-section-hero" data-testid="language-landing-hero">
        <p className="person-eyebrow">Explore</p>
        <h1 data-testid="language-landing-title">{heading}</h1>
        <p className="explore-section-subtitle" data-testid="language-landing-lede">
          {lede}
        </p>
      </section>

      <div className="explore-section-toolbar" data-testid="language-landing-toolbar">
        <MediaBrowseControls
          state={{ ...browse, language: request.code || "" }}
          onChange={updateSearch}
          columns={columns}
          onColumnsChange={setColumns}
          columnScope="language-landing"
          filterOptions={filterOptions}
          sortOptions={sortOptions}
          pageSizes={MEDIA_BROWSE_PAGE_SIZES}
          exportItems
          onExport={exportCurrentPage}
        />
        <div className="explore-section-toolbar-row">
          <div className="explore-section-toolbar-primary">
            {showToolbarPagination ? (
              <p className="explore-section-pagination-summary" data-testid="language-landing-summary">
                {paginationSummary}
              </p>
            ) : null}
            {selected.size ? (
              <p
                className="explore-section-selection-summary"
                data-testid="language-landing-selection-summary"
              >
                {selected.size} selected
                {isOwner && deletePartition.unavailable.length
                  ? ` · ${deletePartition.unavailable.length} not deletable`
                  : ""}
              </p>
            ) : null}
          </div>
          <div className="explore-section-bulk" data-testid="language-landing-bulk">
            <button
              type="button"
              className="ghost"
              data-testid="language-landing-select-all"
              disabled={!pinnableKeys.size || deleteOpen || deleting}
              onClick={selectAllOnPage}
            >
              Select page
            </button>
            <button
              type="button"
              className="ghost"
              data-testid="language-landing-clear-selection"
              disabled={!selected.size || deleteOpen || deleting}
              onClick={clearSelection}
            >
              Clear
            </button>
            <button
              type="button"
              className="ghost"
              data-testid="language-landing-bulk-pin"
              disabled={!selected.size || pinning}
              onClick={handleBulkPin}
            >
              {pinning ? "Pinning…" : `Pin ${selected.size || ""} to watchlist`.trim()}
            </button>
            {isOwner ? (
              <button
                type="button"
                className="btn-danger"
                data-testid="language-landing-bulk-delete"
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
        <p className="status status-secondary explore-section-action-status" data-testid="language-landing-action-status">
          {actionStatus}
        </p>
      ) : null}

      <section className="explore-section-results" data-testid="language-landing-results">
        {view.loading ? <p className="status status-secondary">Loading…</p> : null}
        {view.error ? <p className="error">{view.error}</p> : null}
        {!view.loading && !view.error && !view.items.length ? (
          <p
            className="explore-empty status status-secondary"
            data-testid="language-landing-empty"
          >
            {view.note || NO_MATCHING_TITLES}
          </p>
        ) : null}
        {view.items.length ? (
          <MediaBrowseResults
            state={browse}
            items={view.items}
            columns={columns || undefined}
            selectable
            selected={selected}
            onToggleSelect={toggleSelect}
            getItemKey={libraryBrowseItemKey}
            cardProps={{ testId: "language-landing-card" }}
          />
        ) : null}
      </section>

      {showToolbarPagination ? (
        <MediaBrowsePagination
          summary={paginationSummary}
          pageSize={isAll ? "all" : pageSize}
          pageSizes={MEDIA_BROWSE_PAGE_SIZES}
          onPageSizeChange={(limit) => updateSearch({ limit, offset: 0 })}
          hasPrevious={!isAll && view.offset > 0}
          hasNext={!isAll && view.hasMore}
          onPrevious={() => updateSearch({ offset: Math.max(0, view.offset - pageSize) })}
          onNext={() => updateSearch({ offset: view.offset + pageSize })}
          testIdPrefix="language-landing"
        />
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

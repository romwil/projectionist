import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  addWatchlistPin,
  confirmAction,
  deleteLibraryItems,
  getFeatures,
  getLibraryAggregate,
  proposeAction,
  queryLibrary,
  searchExternal,
} from "../api/client";
import BackLink from "../components/BackLink";
import { useBulkActionProgress } from "../components/BulkActionProgress.jsx";
import BulkLibraryDeleteDialog from "../components/BulkLibraryDeleteDialog.jsx";
import MediaBrowseControls from "../components/MediaBrowseControls";
import MediaBrowseResults from "../components/MediaBrowseResults";
import RecommendModal from "../components/RecommendModal";
import TitleCard from "../components/TitleCard";
import { useAuthGate } from "../components/UserMenu";
import AppShell from "../layouts/AppShell";
import {
  alreadyInArrMessage,
  buildProposeActionBody,
  isAlreadyInArr,
  normalizeUserRole,
  requestPathFromFeatures,
  serviceLabelForTarget,
} from "../lib/addActions.js";
import {
  BEYOND_STATUS,
  beyondCtaLabel,
  beyondEmptyMessage,
  beyondErrorNote,
  beyondSectionSubtitle,
  beyondStatusForError,
  beyondStatusForResult,
  beyondUnavailableNote,
  normalizeExternalResults,
  shouldShowBeyondAffordance,
} from "../lib/beyondSearch.js";
import { ROUTES } from "../lib/browseLinks.js";
import { partitionBulkDeleteSelection } from "../lib/bulkLibraryDelete.js";
import {
  MEDIA_BROWSE_PAGE_SIZES,
  buildMediaBrowseParams,
  isAllPageSize,
  parseMediaBrowse,
  queryFiltersFromBrowse,
  resolvePageSizeLimit,
} from "../lib/mediaBrowse.js";
import { allowWatchlistPin } from "../lib/watchlistPin.js";

function itemKey(item) {
  return `${item?.media_type || ""}:${item?.tmdb_id || item?.rating_key || item?.title || ""}`;
}

function browseHeading(mediaType, q) {
  if (q) return `Search: ${q}`;
  if (mediaType === "movie") return "Movies";
  if (mediaType === "show") return "TV shows";
  return "Browse library";
}

function browseSubtitle(mediaType, q) {
  if (q) return "Titles across your library matching your search";
  if (mediaType === "movie") return "Every movie in your library";
  if (mediaType === "show") return "Every TV show in your library";
  return "Every title in your library";
}

export default function LibraryBrowsePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { isOwner, multiUserEnabled } = useAuthGate();
  const { start, update, finish } = useBulkActionProgress();

  const browse = useMemo(() => parseMediaBrowse(searchParams), [searchParams]);
  const q = (searchParams.get("q") || "").trim();
  const isAll = isAllPageSize(browse.limit);

  const [state, setState] = useState({
    loading: true,
    items: [],
    total: 0,
    returned: 0,
    hasMore: false,
    offset: 0,
    error: "",
  });
  const [columns, setColumns] = useState(null);
  const [filterOptions, setFilterOptions] = useState({ years: [], genres: [] });
  const [recommendItem, setRecommendItem] = useState(null);
  const [selected, setSelected] = useState(() => new Set());
  const [actionStatus, setActionStatus] = useState("");
  const [pinning, setPinning] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [access, setAccess] = useState({
    userRole: "owner",
    requestPath: "arr",
    multiUserEnabled: false,
  });
  const [beyond, setBeyond] = useState({
    status: BEYOND_STATUS.idle,
    items: [],
    total: 0,
  });

  useEffect(() => {
    let cancelled = false;
    getFeatures()
      .then((data) => {
        if (cancelled) return;
        const enabled = Boolean(data?.features?.multi_user_enabled);
        setAccess({
          userRole: normalizeUserRole(data?.user?.role, { multiUserEnabled: enabled }),
          requestPath: requestPathFromFeatures(data),
          multiUserEnabled: enabled,
        });
      })
      .catch(() => {
        if (cancelled) return;
        setAccess({ userRole: "owner", requestPath: "arr", multiUserEnabled: false });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      getLibraryAggregate("year").catch(() => ({ buckets: [] })),
      getLibraryAggregate("genre").catch(() => ({ buckets: [] })),
    ]).then(([yearAgg, genreAgg]) => {
      if (cancelled) return;
      setFilterOptions({
        years: [
          ...new Set((yearAgg?.buckets || []).map((bucket) => bucket.year).filter(Boolean)),
        ].sort((a, b) => b - a),
        genres: [
          ...new Set((genreAgg?.buckets || []).map((bucket) => bucket.genre).filter(Boolean)),
        ].sort(),
      });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setState((prev) => ({ ...prev, loading: true, error: "" }));
    setSelected(new Set());
    setActionStatus("");
    setDeleteOpen(false);
    setDeleteError("");
    setBeyond({ status: BEYOND_STATUS.idle, items: [], total: 0 });

    const filters = queryFiltersFromBrowse(browse);
    // The reader takes year_from/year_to, not a bare year.
    if (browse.year) {
      filters.year_from = browse.year;
      filters.year_to = browse.year;
      delete filters.year;
    }
    if (isAll) {
      filters.limit = resolvePageSizeLimit("all");
      filters.offset = 0;
    }
    if (q) filters.query = q;

    queryLibrary(filters)
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
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setState({
          loading: false,
          items: [],
          total: 0,
          returned: 0,
          hasMore: false,
          offset: 0,
          error: err.message || "Could not load titles.",
        });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [browse, q, isAll]);

  const pinnableKeys = useMemo(
    () => new Set(state.items.filter(allowWatchlistPin).map(itemKey)),
    [state.items],
  );

  const deletePartition = useMemo(
    () => partitionBulkDeleteSelection(state.items, selected, itemKey),
    [state.items, selected],
  );

  const pageSize = isAll ? state.returned || 1 : Number(browse.limit) || 48;
  const page = isAll ? 1 : Math.floor(state.offset / pageSize) + 1;
  const pageCount = isAll ? 1 : Math.max(1, Math.ceil(state.total / pageSize));
  const capped = isAll && state.total > state.returned;

  function updateBrowse(patch) {
    const params = buildMediaBrowseParams(browse, patch);
    if (q) params.set("q", q);
    setSearchParams(params, { replace: true });
  }

  function handleOffset(nextOffset) {
    updateBrowse({ offset: Math.max(0, nextOffset) });
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
    const targets = state.items.filter((item) => selected.has(itemKey(item)) && allowWatchlistPin(item));
    if (!targets.length) return;
    const progressId = start({ label: "Pinning to watchlist", total: targets.length, asynchronous: true });
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

  async function handleBulkDeleteConfirm() {
    if (!isOwner || deleting) return;
    const { ratingKeys, titles } = deletePartition;
    if (!ratingKeys.length) return;
    const progressId = start({ label: "Deleting from library index", total: ratingKeys.length, asynchronous: true });
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
        return {
          ...prev,
          items: nextItems,
          returned: nextItems.length,
          total: Math.max(0, prev.total - deletedCount),
        };
      });
      setSelected(new Set());
      setDeleteOpen(false);
      const summary = deletedCount
        ? `Removed ${deletedCount} title${deletedCount === 1 ? "" : "s"} from the CuratorX library index.`
        : `No matching library records for ${titles.length} selected title${titles.length === 1 ? "" : "s"}.`;
      setActionStatus(summary);
      update(progressId, ratingKeys.length);
      finish(progressId, { label: summary });
    } catch (err) {
      const message = err.message || "Could not delete selected titles.";
      setDeleteError(message);
      finish(progressId, { label: message, state: "error" });
    } finally {
      setDeleting(false);
    }
  }

  async function handleBeyondSearch() {
    if (!q || beyond.status === BEYOND_STATUS.loading) return;
    setBeyond((prev) => ({ ...prev, status: BEYOND_STATUS.loading }));
    try {
      const payload = await searchExternal({ q, mediaType: browse.media_type || "movie" });
      const { items, total } = normalizeExternalResults(payload);
      setBeyond({ status: beyondStatusForResult(payload), items, total });
    } catch (err) {
      setBeyond({ status: beyondStatusForError(err), items: [], total: 0 });
    }
  }

  // TitleCard owns its own add button state; this resolves on success and
  // throws on failure so the card can show Added / Retry.
  async function handleBeyondAdd(item, target) {
    const label = item.title || "this title";
    const service = serviceLabelForTarget(target);
    const proposal = await proposeAction(buildProposeActionBody(item, target));
    if (isAlreadyInArr(proposal)) {
      setActionStatus(alreadyInArrMessage(proposal, { label, service }));
      return proposal;
    }
    const confirm = await confirmAction(proposal.confirmation_token);
    if (isAlreadyInArr(confirm)) {
      setActionStatus(alreadyInArrMessage(confirm, { label, service }));
      return confirm;
    }
    setActionStatus(
      target === "seerr" ? `Requested “${label}” in Seerr.` : `Added “${label}” to ${service}.`,
    );
    return confirm;
  }

  function handleBeyondDismiss(item) {
    setBeyond((prev) => ({
      ...prev,
      items: prev.items.filter((entry) => entry !== item),
    }));
  }

  const hasLibraryResults = state.items.length > 0;
  const showBeyondAffordance = shouldShowBeyondAffordance({
    q,
    unavailable: beyond.status === BEYOND_STATUS.unavailable,
  });
  const beyondBusy = beyond.status === BEYOND_STATUS.loading;
  const beyondActivated = beyond.status !== BEYOND_STATUS.idle;

  const recommendProps = multiUserEnabled
    ? { showRecommend: true, onRecommend: setRecommendItem }
    : { showRecommend: false };

  return (
    <AppShell
      className="app-root explore-section-page library-browse-page"
      testId="library-browse-page"
      variant="browse"
      leading={<BackLink fallbackTo={ROUTES.explore} testId="library-browse-back" />}
      actions={
        <Link to={ROUTES.explore} className="app-topbar-link" data-testid="library-browse-hub-link">
          Explore hub
        </Link>
      }
    >
      <section className="explore-section-hero" data-testid="library-browse-hero">
        <p className="person-eyebrow">Explore</p>
        <h1 data-testid="library-browse-title">{browseHeading(browse.media_type, q)}</h1>
        <p className="explore-section-subtitle">{browseSubtitle(browse.media_type, q)}</p>
      </section>

      <div className="explore-section-toolbar" data-testid="library-browse-toolbar">
        <MediaBrowseControls
          state={browse}
          onChange={updateBrowse}
          columns={columns}
          onColumnsChange={setColumns}
          columnScope="browse"
          filterOptions={filterOptions}
          pageSizes={MEDIA_BROWSE_PAGE_SIZES}
        />
        <div className="explore-section-toolbar-row">
          <div className="explore-section-toolbar-primary">
            <p className="explore-section-pagination-summary" data-testid="library-browse-summary">
              {isAll
                ? capped
                  ? `Showing first ${state.returned} of ${state.total} titles`
                  : `${state.total} title${state.total === 1 ? "" : "s"}`
                : `Page ${page} of ${pageCount}${state.total ? ` · ${state.total} titles` : ""}`}
            </p>
            {selected.size ? (
              <p className="explore-section-selection-summary" data-testid="library-browse-selection-summary">
                {selected.size} selected
                {isOwner && deletePartition.unavailable.length
                  ? ` · ${deletePartition.unavailable.length} not deletable`
                  : ""}
              </p>
            ) : null}
          </div>
          <div className="explore-section-bulk" data-testid="library-browse-bulk">
            <button
              type="button"
              className="ghost"
              data-testid="library-browse-select-all"
              disabled={!pinnableKeys.size}
              onClick={selectAllOnPage}
            >
              Select page
            </button>
            <button
              type="button"
              className="ghost"
              data-testid="library-browse-clear-selection"
              disabled={!selected.size}
              onClick={clearSelection}
            >
              Clear
            </button>
            <button
              type="button"
              className="ghost"
              data-testid="library-browse-bulk-pin"
              disabled={!selected.size || pinning}
              onClick={handleBulkPin}
            >
              {pinning ? "Pinning…" : `Pin ${selected.size || ""} to watchlist`.trim()}
            </button>
            {isOwner ? (
              <button
                type="button"
                className="btn-danger"
                data-testid="library-browse-bulk-delete"
                disabled={!selected.size || !deletePartition.ratingKeys.length || deleting}
                onClick={openBulkDelete}
              >
                Delete
              </button>
            ) : null}
          </div>
        </div>
        {!isAll && (state.hasMore || state.offset > 0) ? (
          <div className="explore-section-toolbar-row explore-section-toolbar-nav">
            <div className="explore-section-page-nav">
              <button
                type="button"
                className="ghost"
                data-testid="library-browse-prev"
                disabled={state.offset <= 0}
                onClick={() => handleOffset(state.offset - pageSize)}
              >
                Previous
              </button>
              <button
                type="button"
                className="ghost"
                data-testid="library-browse-next"
                disabled={!state.hasMore}
                onClick={() => handleOffset(state.offset + pageSize)}
              >
                Next
              </button>
            </div>
          </div>
        ) : null}
      </div>

      {actionStatus ? (
        <p className="status status-secondary explore-section-action-status" data-testid="library-browse-action-status">
          {actionStatus}
        </p>
      ) : null}

      <section className="explore-section-results" data-testid="library-browse-results">
        {state.loading ? <p className="status status-secondary">Loading…</p> : null}
        {state.error ? <p className="error">{state.error}</p> : null}
        {!state.loading && !state.error && !state.items.length ? (
          <p className="explore-empty status status-secondary" data-testid="library-browse-empty">
            {q
              ? `No library titles match “${q}”.`
              : "No titles match these filters yet."}
          </p>
        ) : null}
        {state.items.length ? (
          <MediaBrowseResults
            state={browse}
            items={state.items}
            columns={columns || undefined}
            selectable
            selected={selected}
            onToggleSelect={toggleSelect}
            getItemKey={itemKey}
            cardProps={{ testId: "library-browse-card", ...recommendProps }}
          />
        ) : null}
      </section>

      {showBeyondAffordance ? (
        <section
          className={`explore-beyond ${hasLibraryResults ? "is-secondary" : "is-prominent"}`}
          data-testid="explore-beyond"
        >
          {!beyondActivated ? (
            <div className="explore-beyond-cta" data-testid="explore-beyond-cta">
              <p className="explore-beyond-lead">
                {hasLibraryResults
                  ? "Looking for something you don’t own yet?"
                  : "Not in your library — want to look further afield?"}
              </p>
              <button
                type="button"
                className={hasLibraryResults ? "ghost" : ""}
                data-testid="explore-beyond-button"
                onClick={handleBeyondSearch}
              >
                {beyondCtaLabel({ q })}
              </button>
            </div>
          ) : (
            <>
              <div className="explore-beyond-heading">
                <h2 data-testid="explore-beyond-title">Beyond your collection</h2>
                <p className="explore-section-subtitle">{beyondSectionSubtitle({ q })}</p>
              </div>
              {beyondBusy ? (
                <p className="status status-secondary" data-testid="explore-beyond-loading">
                  Searching beyond your collection…
                </p>
              ) : null}
              {beyond.status === BEYOND_STATUS.error ? (
                <p className="error" data-testid="explore-beyond-error">
                  {beyondErrorNote()}
                </p>
              ) : null}
              {beyond.status === BEYOND_STATUS.empty ? (
                <p
                  className="explore-empty status status-secondary"
                  data-testid="explore-beyond-empty"
                >
                  {beyondEmptyMessage({ q })}
                </p>
              ) : null}
              {beyond.status === BEYOND_STATUS.loaded ? (
                <div className="inline-cards explore-beyond-grid" data-testid="explore-beyond-results">
                  {beyond.items.map((item) => (
                    <TitleCard
                      key={`beyond-${item.media_type}-${item.tmdb_id || item.tvdb_id || item.title}`}
                      item={item}
                      onAdd={handleBeyondAdd}
                      onDismiss={handleBeyondDismiss}
                      requestPath={access.requestPath}
                      userRole={access.userRole}
                      multiUserEnabled={access.multiUserEnabled}
                    />
                  ))}
                </div>
              ) : null}
            </>
          )}
        </section>
      ) : null}

      {beyond.status === BEYOND_STATUS.unavailable ? (
        <p
          className="status status-secondary explore-beyond-note"
          data-testid="explore-beyond-unavailable"
        >
          {beyondUnavailableNote()}
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

      <RecommendModal
        item={recommendItem}
        open={Boolean(recommendItem)}
        onClose={() => setRecommendItem(null)}
      />
    </AppShell>
  );
}

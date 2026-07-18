import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  deleteLibraryItems,
  formatApiError,
  listWatchlist,
  removeWatchlistPin,
  runWatchlistSync,
} from "../api/client";
import BackLink from "../components/BackLink";
import BulkLibraryDeleteDialog from "../components/BulkLibraryDeleteDialog";
import MediaBrowseControls from "../components/MediaBrowseControls";
import MediaBrowseResults from "../components/MediaBrowseResults";
import RecommendModal from "../components/RecommendModal";
import TitleDetailDrawer from "../components/TitleDetailDrawer";
import { useAuthGate } from "../components/UserMenu";
import AppShell from "../layouts/AppShell";
import { ROUTES } from "../lib/backNav.js";
import { partitionBulkDeleteSelection } from "../lib/bulkLibraryDelete.js";
import {
  buildMediaBrowseParams,
  matchesMediaBrowseWatchState,
  mediaBrowseRowsToCsv,
  parseMediaBrowse,
} from "../lib/mediaBrowse.js";
import { titleDetailTargetFromItem } from "../lib/titleDetailDrawer.js";

function pinKey(pin) {
  return String(pin?.id || "");
}

function pinToCardItem(pin) {
  return {
    ...pin,
    in_library: Boolean(pin.in_library),
    rating_key: pin.rating_key || pin.plex_rating_key || null,
  };
}

export default function WatchlistPage() {
  const { isOwner, multiUserEnabled } = useAuthGate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [state, setState] = useState({ loading: true, items: [], error: "" });
  const [columns, setColumns] = useState(null);
  const [selected, setSelected] = useState(() => new Set());
  const [actionStatus, setActionStatus] = useState("");
  const [removing, setRemoving] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [drawerTarget, setDrawerTarget] = useState(null);
  const [recommendItem, setRecommendItem] = useState(null);
  const titleTriggerRef = useRef(null);

  const refresh = useCallback(async ({ pull = false } = {}) => {
    setState((prev) => ({ ...prev, loading: true, error: "" }));
    try {
      if (pull) {
        await runWatchlistSync({ direction: "pull" }).catch(() => {});
      }
      const data = await listWatchlist({ enrich: true });
      setState({
        loading: false,
        items: Array.isArray(data?.items) ? data.items : [],
        error: "",
      });
    } catch (error) {
      setState({
        loading: false,
        items: [],
        error: formatApiError(error),
      });
    }
  }, []);

  useEffect(() => {
    // Local enriched list first — Plex pull belongs on Refresh / Sync settings.
    refresh({ pull: false });
  }, [refresh]);

  const browse = useMemo(() => parseMediaBrowse(searchParams, { sort: "added_at", sort_dir: "desc" }), [searchParams]);
  const sortedItems = useMemo(() => {
    const direction = browse.sort_dir === "desc" ? -1 : 1;
    return [...state.items]
      .filter((item) => !browse.media_type || item?.media_type === browse.media_type)
      .filter((item) => !browse.year || String(item?.year || "") === String(browse.year))
      .filter((item) => matchesMediaBrowseWatchState(item, browse.watch_state))
      .sort((a, b) => {
        const aValue = a?.[browse.sort] ?? (browse.sort === "added_at" ? a?.created_at : "") ?? "";
        const bValue = b?.[browse.sort] ?? (browse.sort === "added_at" ? b?.created_at : "") ?? "";
        return String(aValue).localeCompare(String(bValue), undefined, { numeric: true }) * direction;
      });
  }, [browse, state.items]);

  const cardItems = useMemo(() => sortedItems.map(pinToCardItem), [sortedItems]);

  const deletePartition = useMemo(
    () => partitionBulkDeleteSelection(cardItems, selected, pinKey),
    [cardItems, selected],
  );

  function toggleSelect(pin) {
    const key = pinKey(pin);
    if (!key) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function selectAllOnPage() {
    setSelected(new Set(sortedItems.map(pinKey).filter(Boolean)));
  }

  function clearSelection() {
    setSelected(new Set());
  }

  function handleBrowseChange(patch) {
    setSearchParams(buildMediaBrowseParams(browse, patch), { replace: true });
  }

  function exportCurrentPage(exportColumns) {
    const blob = new Blob([mediaBrowseRowsToCsv(cardItems, exportColumns)], { type: "text/csv;charset=utf-8" });
    const href = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = href;
    link.download = "watchlist.csv";
    link.click();
    URL.revokeObjectURL(href);
  }

  async function handleBulkRemove() {
    if (!selected.size || removing) return;
    const targets = sortedItems.filter((pin) => selected.has(pinKey(pin)));
    if (!targets.length) return;
    setRemoving(true);
    setActionStatus("");
    let ok = 0;
    let failed = 0;
    for (const pin of targets) {
      try {
        await removeWatchlistPin(pin.id);
        ok += 1;
      } catch {
        failed += 1;
      }
    }
    setRemoving(false);
    setSelected(new Set());
    setActionStatus(
      failed
        ? `Removed ${ok}; ${failed} failed.`
        : `Removed ${ok} title${ok === 1 ? "" : "s"} from your watchlist.`,
    );
    await refresh();
  }

  async function handleToggleCardPin(card) {
    const pin = sortedItems.find((item) => pinKey(item) === pinKey(card));
    if (!pin) return;
    await removeWatchlistPin(pin.id);
    setActionStatus("Removed from your watchlist.");
    await refresh();
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
      setDeleteOpen(false);
      setSelected(new Set());
      setActionStatus(
        deletedCount
          ? `Removed ${deletedCount} title${deletedCount === 1 ? "" : "s"} from the CuratorX library index.`
          : `No matching library records for ${titles.length} selected title${titles.length === 1 ? "" : "s"}.`,
      );
      await refresh();
    } catch (err) {
      setDeleteError(err.message || "Could not delete selected titles.");
    } finally {
      setDeleting(false);
    }
  }

  function handleOpenDrawer(pin, trigger) {
    const target = titleDetailTargetFromItem(pinToCardItem(pin));
    if (!target) return;
    titleTriggerRef.current = trigger;
    setDrawerTarget(target);
  }

  return (
    <AppShell
      className="app-root watchlist-page"
      testId="watchlist-page"
      variant="browse"
      leading={<BackLink fallbackTo={ROUTES.chat} testId="watchlist-back" />}
      actions={
        <Link to={ROUTES.watchlistSettings} className="app-topbar-link" data-testid="watchlist-sync-settings">
          Sync settings
        </Link>
      }
    >
      <section className="explore-section-hero watchlist-hero" data-testid="watchlist-hero">
        <p className="person-eyebrow">Watchlist</p>
        <h1 data-testid="watchlist-title">Your watchlist</h1>
        <p className="explore-section-subtitle">
          Plex Discover sync and local pins in one place.{" "}
          <Link to={ROUTES.watchlistSettings} className="watchlist-sync-inline-link">
            Sync settings
          </Link>
        </p>
      </section>

      <div className="explore-section-toolbar watchlist-toolbar" data-testid="watchlist-toolbar">
        <MediaBrowseControls
          state={browse}
          onChange={handleBrowseChange}
          columns={columns}
          onColumnsChange={setColumns}
          columnScope="watchlist"
          exportItems
          onExport={exportCurrentPage}
        />
        <div className="explore-section-toolbar-row">
          <div className="explore-section-toolbar-primary">
            {!state.loading && sortedItems.length ? (
              <p className="explore-section-selection-summary" data-testid="watchlist-count">
                {sortedItems.length} title{sortedItems.length === 1 ? "" : "s"}
                {selected.size ? ` · ${selected.size} selected` : ""}
                {isOwner && selected.size && deletePartition.unavailable.length
                  ? ` · ${deletePartition.unavailable.length} not deletable`
                  : ""}
              </p>
            ) : null}
          </div>
          <div className="explore-section-bulk" data-testid="watchlist-bulk">
            <button
              type="button"
              className="ghost"
              data-testid="watchlist-select-all"
              disabled={!sortedItems.length}
              onClick={selectAllOnPage}
            >
              Select all
            </button>
            <button
              type="button"
              className="ghost"
              data-testid="watchlist-clear-selection"
              disabled={!selected.size}
              onClick={clearSelection}
            >
              Clear
            </button>
            <button
              type="button"
              className="ghost"
              data-testid="watchlist-bulk-remove"
              disabled={!selected.size || removing}
              onClick={handleBulkRemove}
            >
              {removing ? "Removing…" : "Remove"}
            </button>
            {isOwner ? (
              <button
                type="button"
                className="btn-danger"
                data-testid="watchlist-bulk-delete"
                disabled={!selected.size || !deletePartition.ratingKeys.length || deleting}
                onClick={openBulkDelete}
              >
                Delete
              </button>
            ) : null}
            <button
              type="button"
              className="ghost"
              data-testid="watchlist-refresh"
              disabled={state.loading}
              onClick={() => refresh({ pull: true })}
            >
              {state.loading ? "Refreshing…" : "Refresh"}
            </button>
          </div>
        </div>
      </div>

      {actionStatus ? (
        <p className="status status-secondary explore-section-action-status" data-testid="watchlist-action-status">
          {actionStatus}
        </p>
      ) : null}

      <section className="explore-section-results watchlist-results" data-testid="watchlist-results">
        {state.loading ? <p className="status status-secondary">Loading watchlist…</p> : null}
        {state.error ? <p className="error">{state.error}</p> : null}
        {!state.loading && !state.error && !sortedItems.length ? (
          <div className="watchlist-empty" data-testid="watchlist-empty">
            <h2 className="watchlist-empty-title">Nothing pinned yet</h2>
            <p className="status status-secondary">
              Pin titles from chat or turn on Plex Discover sync to import your Plex watchlist.
            </p>
            <div className="watchlist-empty-actions">
              <Link to={ROUTES.chat}>Back to chat</Link>
              <Link to={ROUTES.watchlistSettings}>Sync settings</Link>
            </div>
          </div>
        ) : null}
        {sortedItems.length ? (
          <MediaBrowseResults
            state={browse}
            items={cardItems}
            columns={columns || undefined}
            selectable
            selected={selected}
            onToggleSelect={(card) => {
              const pin = sortedItems.find((item) => pinKey(item) === pinKey(card));
              if (pin) toggleSelect(pin);
            }}
            cardProps={{
              testId: "watchlist-title-card",
              pinned: true,
              onTogglePin: handleToggleCardPin,
              showRecommend: multiUserEnabled,
              onRecommend: multiUserEnabled ? setRecommendItem : undefined,
              onOpenDetail: (card, event) => {
                const pin = sortedItems.find((item) => pinKey(item) === pinKey(card));
                if (pin && titleDetailTargetFromItem(card)) handleOpenDrawer(pin, event.currentTarget);
              },
            }}
          />
        ) : null}
      </section>

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

      <TitleDetailDrawer
        open={Boolean(drawerTarget)}
        target={drawerTarget}
        returnFocusRef={titleTriggerRef}
        onClose={() => setDrawerTarget(null)}
        onDeleted={() => refresh()}
      />
      <RecommendModal
        item={recommendItem}
        open={Boolean(recommendItem)}
        onClose={() => setRecommendItem(null)}
      />
    </AppShell>
  );
}

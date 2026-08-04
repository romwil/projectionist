import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  getLibraryOverview,
  getLibraryAggregate,
  getLibraryHealth,
  getLibraryStats,
  getPurgeCandidates,
  refreshPurgeCandidates,
  enrichPurgeCandidates,
  listReviews,
  deletePurgeCandidates,
  dismissPurgeCandidates,
} from "../api/client";
import BarChart from "../components/charts/BarChart";
import DonutChart from "../components/charts/DonutChart";
import Gauge from "../components/charts/Gauge";
import { useBulkActionProgress } from "../components/BulkActionProgress";
import BulkLibraryDeleteDialog from "../components/BulkLibraryDeleteDialog";
import KnowledgeCoverageCard from "../components/KnowledgeCoverageCard";
import OwnerHealthHero from "../components/OwnerHealthHero";
import OwnerNowPlayingBreakdown from "../components/OwnerNowPlayingBreakdown";
import RemovalSummaryDialog from "../components/RemovalSummaryDialog.jsx";
import SectionHelp from "../components/SectionHelp.jsx";
import WeeklyDigestPanel from "../components/WeeklyDigestPanel";
import GroomingUndoPanel from "../components/GroomingUndoPanel";
import TitleDetailDrawer from "../components/TitleDetailDrawer";
import {
  BULK_DELETE_EMPTY_SELECTION_MESSAGE,
  LIBRARY_DELETE_MODE_FULL,
  formatBulkLibraryDeleteResultMessage,
  hasRemovalSummary,
} from "../lib/bulkLibraryDelete.js";
import {
  buildRuntimeBuckets,
  filterPurgeCandidatesByMediaType,
  sortPurgeCandidates,
} from "../lib/dashboardCharts.js";
import { titleDetailTargetFromPurgeCandidate } from "../lib/titleDetailDrawer.js";

const PURGE_MEDIA_TABS = [
  { id: "all", label: "All", mediaType: null },
  { id: "movie", label: "Movies", mediaType: "movie" },
  { id: "show", label: "TV", mediaType: "show" },
];

function useDashData(fetcher) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetcher()
      .then((d) => setData(d))
      .catch((e) => setError(e.message || "Failed"))
      .finally(() => setLoading(false));
  }, [fetcher]);
  useEffect(() => { load(); }, [load]);
  return { data, loading, error, reload: load };
}

function Panel({ title, loading, error, children }) {
  return (
    <section className="dash-panel">
      <h3 className="dash-panel-title">{title}</h3>
      {loading ? (
        <div className="dash-skeleton" aria-label="Loading">
          <div className="dash-skeleton-bar" />
          <div className="dash-skeleton-bar short" />
          <div className="dash-skeleton-bar" />
        </div>
      ) : error ? (
        <p className="dash-panel-error">{error}</p>
      ) : (
        children
      )}
    </section>
  );
}

function StatCard({ value, label, detail, accent }) {
  return (
    <div className="dash-stat-card">
      <span className="dash-stat-value" style={accent ? { color: accent } : undefined}>
        {value}
      </span>
      <span className="dash-stat-label">{label}</span>
      {detail ? <span className="dash-stat-detail">{detail}</span> : null}
    </div>
  );
}

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return "—";
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(0)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

function formatPurgeGeneratedAt(generatedAt) {
  if (generatedAt == null || generatedAt === "") return null;
  const ms = typeof generatedAt === "number" ? generatedAt * 1000 : Date.parse(generatedAt);
  if (!Number.isFinite(ms)) return null;
  try {
    return new Date(ms).toLocaleString();
  } catch {
    return null;
  }
}

function PurgeTable({
  candidates,
  onRefresh,
  stale = false,
  generatedAt = null,
  pageSize = 20,
  bufferTarget = 100,
  refilling = false,
  onRefreshNow,
  onGroomingChanged,
}) {
  const { start, update, finish } = useBulkActionProgress();
  const [sortKey, setSortKey] = useState("purge_score");
  const [sortDir, setSortDir] = useState("desc");
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState(new Set());
  const [confirmAction, setConfirmAction] = useState(null);
  const [purgeDialogOpen, setPurgeDialogOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [purgeError, setPurgeError] = useState("");
  const [removalSummary, setRemovalSummary] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [drawerTarget, setDrawerTarget] = useState(null);
  const [mediaTypeFilter, setMediaTypeFilter] = useState(null);
  const [enrichedByKey, setEnrichedByKey] = useState({});
  const titleTriggerRef = useRef(null);
  const filtered = filterPurgeCandidatesByMediaType(candidates, mediaTypeFilter);
  const sorted = sortPurgeCandidates(filtered, sortKey, sortDir);
  const effectivePageSize = Math.max(1, Number(pageSize) || 20);
  const pageCount = Math.max(1, Math.ceil(sorted.length / effectivePageSize) || 1);
  const safePage = Math.min(page, pageCount - 1);
  const pageStart = safePage * effectivePageSize;
  const displayed = sorted.slice(pageStart, pageStart + effectivePageSize).map((c) => {
    const key = String(c?.rating_key || "");
    return key && enrichedByKey[key] ? { ...c, ...enrichedByKey[key] } : c;
  });
  const displayedKeys = displayed.map((c) => c.rating_key).join("|");
  const generatedLabel = formatPurgeGeneratedAt(generatedAt);
  const selectedItems = displayed.filter((c) => selected.has(c.rating_key));
  const selectedTitles = selectedItems.map(
    (c) => String(c?.title || "Untitled").trim() || "Untitled",
  );
  const activeMediaTab =
    PURGE_MEDIA_TABS.find((tab) => tab.mediaType === mediaTypeFilter)?.id || "all";

  useEffect(() => {
    setPage(0);
    setSelected(new Set());
  }, [candidates, mediaTypeFilter]);

  useEffect(() => {
    const keys = displayed
      .map((c) => String(c?.rating_key || "").trim())
      .filter(Boolean);
    if (!keys.length) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const payload = await enrichPurgeCandidates(keys);
        if (cancelled) return;
        const next = {};
        for (const item of payload?.items || []) {
          const key = String(item?.rating_key || "").trim();
          if (key) next[key] = item;
        }
        setEnrichedByKey((prev) => ({ ...prev, ...next }));
      } catch {
        // Enrichment is best-effort; keep cached row values.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [safePage, displayedKeys]);

  async function handleRefreshNow() {
    if (refreshing || !onRefreshNow) return;
    setRefreshing(true);
    try {
      await onRefreshNow();
    } finally {
      setRefreshing(false);
    }
  }

  function handleSort(key) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
    setPage(0);
  }

  function toggleSelect(ratingKey) {
    if (purgeDialogOpen || actionLoading) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(ratingKey)) next.delete(ratingKey);
      else next.add(ratingKey);
      return next;
    });
  }

  function toggleSelectAll() {
    if (purgeDialogOpen || actionLoading) return;
    if (selected.size === displayed.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(displayed.map((c) => c.rating_key)));
    }
  }

  async function handlePurgeConfirm({ mode } = {}) {
    const keys = [...selected];
    if (!keys.length) {
      setPurgeError(BULK_DELETE_EMPTY_SELECTION_MESSAGE);
      return;
    }
    const progressId = start({
      label: "Purging selected titles",
      total: keys.length,
      asynchronous: true,
    });
    setActionLoading(true);
    setPurgeError("");
    try {
      const result = await deletePurgeCandidates(keys, { mode });
      const errors = Array.isArray(result?.errors) ? result.errors : [];
      const deleted = Number(result?.deleted) || 0;
      const message = formatBulkLibraryDeleteResultMessage(result, {
        titles: selectedTitles,
      });
      update(progressId, keys.length);
      if (errors.length && deleted <= 0) {
        setPurgeError(message);
        finish(progressId, { label: message, state: "error" });
        onRefresh?.();
        return;
      }
      finish(progressId, { label: message });
      setSelected(new Set());
      setPurgeDialogOpen(false);
      if (hasRemovalSummary(result)) setRemovalSummary(result);
      onRefresh?.();
      onGroomingChanged?.();
    } catch (err) {
      const message = err?.message || "Could not complete the purge.";
      setPurgeError(message);
      finish(progressId, { label: message, state: "error" });
    } finally {
      setActionLoading(false);
    }
  }

  async function handleConfirmedDismiss() {
    const keys = [...selected];
    if (!keys.length) return;
    const progressId = start({
      label: "Keeping selected titles",
      total: keys.length,
      asynchronous: true,
    });
    setActionLoading(true);
    try {
      await dismissPurgeCandidates(keys);
      update(progressId, keys.length);
      finish(progressId, {
        label: `Kept ${keys.length} title${keys.length === 1 ? "" : "s"} out of purge suggestions.`,
      });
      setSelected(new Set());
      onRefresh?.();
      onGroomingChanged?.();
    } catch {
      finish(progressId, { label: "Could not complete the bulk action.", state: "error" });
    } finally {
      setActionLoading(false);
      setConfirmAction(null);
    }
  }

  const arrow = (key) => (sortKey === key ? (sortDir === "asc" ? " ↑" : " ↓") : "");

  function handleDrawerDeleted(payload) {
    // RemovalSummaryDialog lives on TitleDetailDrawer for this path — do not
    // open a second copy here. Still refresh the grid immediately.
    if (!hasRemovalSummary(payload?.result) && payload?.notice) {
      const progressId = start({
        label: payload.notice,
        total: 1,
        asynchronous: true,
      });
      finish(progressId, { label: payload.notice });
    }
    onRefresh?.();
    onGroomingChanged?.();
  }

  const filterEmpty =
    Boolean(candidates?.length) && !sorted.length && Boolean(mediaTypeFilter);

  return (
    <div className="dash-purge-container">
      <div className="dash-purge-toolbar">
        <p className="dash-purge-meta" data-testid="purge-cache-meta">
          {stale
            ? "Cache empty — run Refresh now to compute candidates."
            : generatedLabel
              ? `Cached ${generatedLabel} · ${filtered.length}/${bufferTarget || 100} shown${
                  mediaTypeFilter ? ` (${mediaTypeFilter === "show" ? "TV" : "movies"})` : " buffered"
                }`
              : filtered.length
                ? `Showing ${filtered.length} candidates${
                    mediaTypeFilter ? ` (${mediaTypeFilter === "show" ? "TV" : "movies"})` : ""
                  }`
                : "No purge candidates in cache."}
          {refilling ? " · Refilling…" : ""}
        </p>
        <button
          type="button"
          className="dash-purge-btn dash-purge-btn--muted"
          data-testid="purge-refresh-now"
          disabled={refreshing}
          onClick={handleRefreshNow}
        >
          {refreshing ? "Refreshing…" : "Refresh now"}
        </button>
      </div>

      <div
        className="explore-media-tabs dash-purge-media-tabs"
        role="tablist"
        aria-label="Filter purge candidates by media type"
        data-testid="purge-media-tabs"
      >
        {PURGE_MEDIA_TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeMediaTab === tab.id}
            className={`explore-media-tab${activeMediaTab === tab.id ? " is-active" : ""}`}
            data-testid={`purge-media-tab-${tab.id}`}
            onClick={() => setMediaTypeFilter(tab.mediaType)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {!sorted.length ? (
        <p className="dash-empty" data-testid="purge-empty">
          {stale
            ? "Purge candidates have not been computed yet."
            : filterEmpty
              ? `No ${mediaTypeFilter === "show" ? "TV show" : "movie"} purge candidates in the current buffer.`
              : "No purge candidates found."}
        </p>
      ) : null}

      {selected.size > 0 && (
        <div className="dash-purge-actions">
          <button
            type="button"
            className="dash-purge-btn dash-purge-btn--danger"
            data-testid="purge-selected"
            onClick={() => {
              setPurgeError("");
              setPurgeDialogOpen(true);
            }}
          >
            Purge Selected <span className="dash-purge-badge">{selected.size}</span>
          </button>
          <button
            type="button"
            className="dash-purge-btn dash-purge-btn--muted"
            data-testid="purge-keep-selected"
            onClick={() => setConfirmAction("dismiss")}
          >
            Keep Selected <span className="dash-purge-badge">{selected.size}</span>
          </button>
        </div>
      )}

      {confirmAction === "dismiss" && (
        <div className="dash-purge-confirm" role="alertdialog" aria-label="Confirm keep">
          <p>
            Keep {selected.size} title{selected.size > 1 ? "s" : ""} out of purge suggestions?
            They won&apos;t appear again.
          </p>
          <div className="dash-purge-confirm-actions">
            <button
              type="button"
              className="dash-purge-btn dash-purge-btn--danger"
              disabled={actionLoading}
              onClick={handleConfirmedDismiss}
            >
              {actionLoading ? "Processing…" : "Confirm"}
            </button>
            <button
              type="button"
              className="dash-purge-btn dash-purge-btn--muted"
              disabled={actionLoading}
              onClick={() => setConfirmAction(null)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <BulkLibraryDeleteDialog
        open={purgeDialogOpen}
        titles={selectedTitles}
        loading={actionLoading}
        error={purgeError}
        defaultMode={LIBRARY_DELETE_MODE_FULL}
        surface="purge"
        onCancel={() => {
          if (actionLoading) return;
          setPurgeDialogOpen(false);
          setPurgeError("");
        }}
        onConfirm={handlePurgeConfirm}
      />

      <RemovalSummaryDialog
        open={Boolean(removalSummary)}
        result={removalSummary}
        onClose={() => setRemovalSummary(null)}
      />

      {sorted.length ? (
        <>
          <div className="dash-table-wrap">
            <table className="dash-table">
              <thead>
                <tr>
                  <th className="dash-table-check">
                    <input
                      type="checkbox"
                      checked={displayed.length > 0 && selected.size === displayed.length}
                      disabled={purgeDialogOpen || actionLoading}
                      onChange={toggleSelectAll}
                      aria-label="Select all"
                    />
                  </th>
                  <th onClick={() => handleSort("title")}>Title{arrow("title")}</th>
                  <th onClick={() => handleSort("media_type")}>Type{arrow("media_type")}</th>
                  <th onClick={() => handleSort("file_size")}>Size{arrow("file_size")}</th>
                  <th onClick={() => handleSort("last_watched")}>Last Watched{arrow("last_watched")}</th>
                  <th onClick={() => handleSort("taste_match")}>Taste %{arrow("taste_match")}</th>
                  <th onClick={() => handleSort("purge_score")}>Score{arrow("purge_score")}</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {displayed.map((c, i) => (
                  <tr key={c.rating_key || c.title + i} className={selected.has(c.rating_key) ? "dash-table-row--selected" : ""}>
                    <td className="dash-table-check">
                      <input
                        type="checkbox"
                        checked={selected.has(c.rating_key)}
                        disabled={purgeDialogOpen || actionLoading}
                        onChange={() => toggleSelect(c.rating_key)}
                        aria-label={`Select ${c.title}`}
                      />
                    </td>
                    <td className="dash-table-title">
                      {titleDetailTargetFromPurgeCandidate(c) ? (
                        <button
                          type="button"
                          className="dash-table-title-btn"
                          data-testid="purge-candidate-title"
                          onClick={(event) => {
                            const target = titleDetailTargetFromPurgeCandidate(c);
                            if (!target) return;
                            titleTriggerRef.current = event.currentTarget;
                            setDrawerTarget(target);
                          }}
                        >
                          {c.title}
                        </button>
                      ) : (
                        c.title
                      )}
                    </td>
                    <td data-testid="purge-candidate-type">
                      {String(c.media_type || "").toLowerCase() === "show" ? "Show" : "Movie"}
                    </td>
                    <td>{formatBytes(c.file_size)}</td>
                    <td>{c.last_watched || "Never"}</td>
                    <td>{c.taste_match != null ? `${Math.round(c.taste_match)}%` : "—"}</td>
                    <td>{c.purge_score != null ? c.purge_score.toFixed(1) : "—"}</td>
                    <td className="dash-table-reason">{c.reason || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="dash-purge-pagination" data-testid="purge-pagination">
            <button
              type="button"
              className="dash-purge-btn dash-purge-btn--muted"
              disabled={safePage <= 0 || actionLoading}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >
              Previous
            </button>
            <span className="dash-purge-meta">
              Page {safePage + 1} of {pageCount}
            </span>
            <button
              type="button"
              className="dash-purge-btn dash-purge-btn--muted"
              disabled={safePage >= pageCount - 1 || actionLoading}
              onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
            >
              Next
            </button>
          </div>
        </>
      ) : null}

      <TitleDetailDrawer
        open={Boolean(drawerTarget)}
        target={drawerTarget}
        returnFocusRef={titleTriggerRef}
        onClose={() => setDrawerTarget(null)}
        onDeleted={handleDrawerDeleted}
        deleteDefaultMode={LIBRARY_DELETE_MODE_FULL}
        deleteSurface="purge"
      />
    </div>
  );
}

const fetchOverview = () => getLibraryOverview();
const fetchHealth = () => getLibraryHealth();
const fetchStats = () => getLibraryStats();
const fetchPurge = () => getPurgeCandidates();
const fetchReviews = () => listReviews({ limit: 10, sort: "newest" });
const fetchRuntimeAgg = () => getLibraryAggregate("runtime_bucket");
const fetchDecadeAgg = () => getLibraryAggregate("decade");
const fetchGenreAgg = () => getLibraryAggregate("genre");
const fetchCountryAgg = () => getLibraryAggregate("country");
const fetchLanguageAgg = () => getLibraryAggregate("language");

export default function DashboardPage() {
  const overview = useDashData(fetchOverview);
  const health = useDashData(fetchHealth);
  const stats = useDashData(fetchStats);
  const purge = useDashData(fetchPurge);
  const reviews = useDashData(fetchReviews);
  const runtimeAgg = useDashData(fetchRuntimeAgg);
  const decadeAgg = useDashData(fetchDecadeAgg);
  const genreAgg = useDashData(fetchGenreAgg);
  const countryAgg = useDashData(fetchCountryAgg);
  const languageAgg = useDashData(fetchLanguageAgg);
  const [groomingEpoch, setGroomingEpoch] = useState(0);

  async function handlePurgeRefreshNow() {
    const payload = await refreshPurgeCandidates();
    purge.reload();
    return payload;
  }

  function refreshAll() {
    overview.reload();
    health.reload();
    stats.reload();
    purge.reload();
    reviews.reload();
    runtimeAgg.reload();
    decadeAgg.reload();
    genreAgg.reload();
    countryAgg.reload();
    languageAgg.reload();
  }

  const ov = overview.data;
  const hlth = health.data;
  const st = stats.data;

  const decadeData = extractAggData(decadeAgg.data);
  const genreData = extractAggData(genreAgg.data).slice(0, 10);
  const countryData = extractAggData(countryAgg.data).slice(0, 5);
  const languageData = extractAggData(languageAgg.data).slice(0, 5);
  const runtimeBuckets = buildRuntimeBuckets(extractAggData(runtimeAgg.data));

  const movieCount = st?.movies ?? ov?.movies ?? 0;
  const showCount = st?.shows ?? ov?.shows ?? 0;

  const unwatchedPct = hlth?.unwatched_pct ?? ov?.unwatched_pct ?? 0;
  const staleAdds = hlth?.stale_adds ?? 0;
  const ratingCoverage = hlth?.rating_coverage_pct ?? 0;
  const ratingCoverageNote = hlth?.rating_coverage_note || null;

  const purgeCandidates = Array.isArray(purge.data)
    ? purge.data
    : purge.data?.candidates ?? purge.data?.items ?? [];
  const purgeStale = Boolean(purge.data && !Array.isArray(purge.data) && purge.data.stale);
  const purgeGeneratedAt = Array.isArray(purge.data) ? null : purge.data?.generated_at ?? null;
  const purgePageSize = Array.isArray(purge.data) ? 20 : Number(purge.data?.page_size) || 20;
  const purgeBufferTarget = Array.isArray(purge.data)
    ? 100
    : Number(purge.data?.buffer_target) || 100;
  const purgeRefilling = Boolean(
    !Array.isArray(purge.data) && purge.data?.refilling,
  );

  const recentReviews = Array.isArray(reviews.data)
    ? reviews.data
    : reviews.data?.reviews ?? reviews.data?.items ?? [];

  return (
    <div className="dash-page" data-testid="dashboard-page">
      <header className="dash-header">
        <div>
          <h1 className="dash-title">Library intelligence</h1>
        </div>
        <button type="button" className="ghost" onClick={refreshAll}>
          Refresh
        </button>
      </header>

      <OwnerHealthHero health={hlth} />

      <OwnerNowPlayingBreakdown />

      <WeeklyDigestPanel />

      {/* ─── Panel 1: Library Composition ─── */}
      <div className="dash-grid">
        <Panel
          title="Decade Distribution"
          loading={decadeAgg.loading}
          error={decadeAgg.error}
        >
          <BarChart data={decadeData} />
        </Panel>

        <Panel
          title="Top Genres"
          loading={genreAgg.loading}
          error={genreAgg.error}
        >
          <BarChart data={genreData} />
        </Panel>

        <Panel
          title="Movies vs Shows"
          loading={stats.loading && overview.loading}
          error={stats.error && overview.error}
        >
          {movieCount || showCount ? (
            <DonutChart
              segments={[
                { label: "Movies", value: movieCount },
                { label: "Shows", value: showCount },
              ]}
            />
          ) : (
            <p className="dash-empty">No library data.</p>
          )}
        </Panel>

        <Panel
          title="Countries"
          loading={countryAgg.loading}
          error={countryAgg.error}
        >
          <BarChart data={countryData} barHeight={20} />
        </Panel>

        <Panel
          title="Languages"
          loading={languageAgg.loading}
          error={languageAgg.error}
        >
          <BarChart data={languageData} barHeight={20} />
        </Panel>

        <Panel
          title="Runtime Distribution"
          loading={runtimeAgg.loading}
          error={runtimeAgg.error}
        >
          <BarChart data={runtimeBuckets} />
        </Panel>
      </div>

      {/* ─── Knowledge depth (Phase D) ─── */}
      <div className="dash-section-heading">
        <h2 className="dash-section-title">Curator knowledge</h2>
        <SectionHelp label="About curator knowledge" testId="knowledge-section-help">
          <p>
            These bars show how thoroughly Projectionist has learned your shelves —
            overviews, plot motifs, keywords, and neighbors. Sparse coverage just means
            idle enrichment tasks still have work; it is not a library problem.
          </p>
        </SectionHelp>
      </div>
      <KnowledgeCoverageCard variant="panel" />

      {/* ─── Panel 2: Health ─── */}
      <h2 className="dash-section-title">Library health</h2>
      <div className="dash-grid">
        <Panel title="Unwatched" loading={health.loading} error={health.error}>
          <Link
            className="dash-metric-link"
            to="/explore/browse?watch_state=unwatched&sort=added_at&sort_dir=asc"
            data-testid="dash-health-unwatched"
          >
            <Gauge value={unwatchedPct} label="Unwatched titles" />
          </Link>
        </Panel>

        <Panel title="Stale Adds" loading={health.loading} error={health.error}>
          <Link
            className="dash-metric-link"
            to="/explore/browse?watch_state=unwatched&sort=added_at&sort_dir=asc"
            data-testid="dash-health-stale"
          >
            <StatCard
              value={staleAdds}
              label="Stale titles"
              detail="Added 90+ days ago, never watched"
            />
          </Link>
        </Panel>

        <Panel title="Rating Coverage" loading={health.loading} error={health.error}>
          <Link
            className="dash-metric-link"
            to="/explore/browse?watch_state=watched"
            data-testid="dash-health-rating"
          >
            <Gauge
              value={ratingCoverage}
              label={ratingCoverageNote || "Watched titles rated"}
              invert
            />
          </Link>
        </Panel>
      </div>

      {/* ─── Panel 3: Storage Intelligence ─── */}
      <div className="dash-section-heading" id="storage-intelligence">
        <h2 className="dash-section-title">Storage Intelligence</h2>
        <SectionHelp label="About Storage Intelligence" testId="purge-section-help">
          <p>
            Purge candidates are titles that look stale or low-signal — good prune
            targets when you need disk space. Filter by Movies or TV, then select rows
            and purge: full remove deletes files through Radarr/Sonarr; index-only only
            drops Projectionist&apos;s copy (undoable from the maintenance panel below).
          </p>
        </SectionHelp>
      </div>
      <Panel title="Purge Candidates" loading={purge.loading} error={purge.error}>
        <PurgeTable
          candidates={purgeCandidates}
          onRefresh={purge.reload}
          stale={purgeStale}
          generatedAt={purgeGeneratedAt}
          pageSize={purgePageSize}
          bufferTarget={purgeBufferTarget}
          refilling={purgeRefilling}
          onRefreshNow={handlePurgeRefreshNow}
          onGroomingChanged={() => setGroomingEpoch((n) => n + 1)}
        />
      </Panel>

      {/* ─── Purge candidate refresh + index-only undo (below the grid) ─── */}
      <GroomingUndoPanel key={groomingEpoch} onChanged={purge.reload} />

      {/* ─── Panel 4: Taste ─── */}
      <h2 className="dash-section-title">Taste</h2>
      <Panel title="Recent ratings" loading={reviews.loading} error={reviews.error}>
        {recentReviews.length ? (
          <ul className="dash-timeline">
            {recentReviews.slice(0, 10).map((r, i) => {
              const starVal = r.stars ?? r.rating;
              return (
                <li key={r.id ?? i} className="dash-timeline-item">
                  <span className="dash-timeline-icon">
                    {starVal ? "★" : r.dismissed ? "✕" : "♥"}
                  </span>
                  <div className="dash-timeline-body">
                    <strong>{r.title || r.media_title || "Untitled"}</strong>
                    {starVal ? (
                      <span className="dash-timeline-meta">{"★".repeat(Math.round(starVal))}{starVal}/5</span>
                    ) : null}
                    {r.review_text ? (
                      <span className="dash-timeline-detail">
                        {r.review_text.length > 80
                          ? r.review_text.slice(0, 77) + "…"
                          : r.review_text}
                      </span>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="dash-empty">No recent ratings yet.</p>
        )}
      </Panel>
    </div>
  );
}

function extractAggData(raw) {
  if (!raw) return [];
  const arr = Array.isArray(raw)
    ? raw
    : raw.buckets ?? raw.groups ?? raw.data ?? raw.results ?? [];
  return arr.map((d) => ({
    label:
      d.label ?? d.group ?? d.name ?? d.decade ?? d.genre ?? d.bucket ?? d.key ?? String(d.value ?? ""),
    value: d.count ?? d.total ?? 0,
  }));
}

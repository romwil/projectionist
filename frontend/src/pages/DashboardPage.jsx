import { useCallback, useEffect, useRef, useState } from "react";
import {
  getLibraryOverview,
  getLibraryAggregate,
  getLibraryHealth,
  getLibraryStats,
  getPurgeCandidates,
  refreshPurgeCandidates,
  getEngagementStreak,
  listReviews,
  deletePurgeCandidates,
  dismissPurgeCandidates,
} from "../api/client";
import BarChart from "../components/charts/BarChart";
import DonutChart from "../components/charts/DonutChart";
import Gauge from "../components/charts/Gauge";
import { useBulkActionProgress } from "../components/BulkActionProgress";
import KnowledgeCoverageCard from "../components/KnowledgeCoverageCard";
import OwnerHealthHero from "../components/OwnerHealthHero";
import WeeklyDigestPanel from "../components/WeeklyDigestPanel";
import GroomingUndoPanel from "../components/GroomingUndoPanel";
import TitleDetailDrawer from "../components/TitleDetailDrawer";
import { buildRuntimeBuckets, sortPurgeCandidates } from "../lib/dashboardCharts.js";
import { titleDetailTargetFromPurgeCandidate } from "../lib/titleDetailDrawer.js";

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

function PurgeTable({ candidates, onRefresh, stale = false, generatedAt = null, onRefreshNow }) {
  const { start, update, finish } = useBulkActionProgress();
  const [sortKey, setSortKey] = useState("purge_score");
  const [sortDir, setSortDir] = useState("desc");
  const [selected, setSelected] = useState(new Set());
  const [confirmAction, setConfirmAction] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [drawerTarget, setDrawerTarget] = useState(null);
  const titleTriggerRef = useRef(null);
  const sorted = sortPurgeCandidates(candidates, sortKey, sortDir);
  const displayed = sorted.slice(0, 20);
  const generatedLabel = formatPurgeGeneratedAt(generatedAt);

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
  }

  function toggleSelect(ratingKey) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(ratingKey)) next.delete(ratingKey);
      else next.add(ratingKey);
      return next;
    });
  }

  function toggleSelectAll() {
    if (selected.size === displayed.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(displayed.map((c) => c.rating_key)));
    }
  }

  async function handleConfirmedAction() {
    const keys = [...selected];
    if (!keys.length) return;
    const actionLabel = confirmAction === "delete" ? "Deleting purge candidates" : "Dismissing purge candidates";
    const progressId = start({ label: actionLabel, total: keys.length, asynchronous: true });
    setActionLoading(true);
    try {
      if (confirmAction === "delete") {
        await deletePurgeCandidates(keys);
      } else if (confirmAction === "dismiss") {
        await dismissPurgeCandidates(keys);
      }
      update(progressId, keys.length);
      finish(progressId, {
        label: `${confirmAction === "delete" ? "Deleted" : "Dismissed"} ${keys.length} purge candidate${keys.length === 1 ? "" : "s"}.`,
      });
      setSelected(new Set());
      onRefresh?.();
    } catch {
      finish(progressId, { label: "Could not complete the bulk action.", state: "error" });
    } finally {
      setActionLoading(false);
      setConfirmAction(null);
    }
  }

  const arrow = (key) => (sortKey === key ? (sortDir === "asc" ? " ↑" : " ↓") : "");

  return (
    <div className="dash-purge-container">
      <div className="dash-purge-toolbar">
        <p className="dash-purge-meta" data-testid="purge-cache-meta">
          {stale
            ? "Cache empty — run Refresh now to compute candidates."
            : generatedLabel
              ? `Cached ${generatedLabel}`
              : sorted.length
                ? "Showing cached candidates"
                : "No purge candidates in cache."}
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

      {!sorted.length ? (
        <p className="dash-empty" data-testid="purge-empty">
          {stale
            ? "Purge candidates have not been computed yet."
            : "No purge candidates found."}
        </p>
      ) : null}

      {selected.size > 0 && (
        <div className="dash-purge-actions">
          <button
            type="button"
            className="dash-purge-btn dash-purge-btn--danger"
            onClick={() => setConfirmAction("delete")}
          >
            Delete Selected <span className="dash-purge-badge">{selected.size}</span>
          </button>
          <button
            type="button"
            className="dash-purge-btn dash-purge-btn--muted"
            onClick={() => setConfirmAction("dismiss")}
          >
            Dismiss Selected <span className="dash-purge-badge">{selected.size}</span>
          </button>
        </div>
      )}

      {confirmAction && (
        <div className="dash-purge-confirm" role="alertdialog" aria-label="Confirm action">
          <p>
            {confirmAction === "delete"
              ? `Are you sure you want to remove ${selected.size} title${selected.size > 1 ? "s" : ""} from your library?`
              : `Dismiss ${selected.size} title${selected.size > 1 ? "s" : ""} from purge suggestions? They won't appear again.`}
          </p>
          <div className="dash-purge-confirm-actions">
            <button
              type="button"
              className="dash-purge-btn dash-purge-btn--danger"
              disabled={actionLoading}
              onClick={handleConfirmedAction}
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

      {sorted.length ? (
        <div className="dash-table-wrap">
          <table className="dash-table">
            <thead>
              <tr>
                <th className="dash-table-check">
                  <input
                    type="checkbox"
                    checked={displayed.length > 0 && selected.size === displayed.length}
                    onChange={toggleSelectAll}
                    aria-label="Select all"
                  />
                </th>
                <th onClick={() => handleSort("title")}>Title{arrow("title")}</th>
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
      ) : null}

      <TitleDetailDrawer
        open={Boolean(drawerTarget)}
        target={drawerTarget}
        returnFocusRef={titleTriggerRef}
        onClose={() => setDrawerTarget(null)}
        onDeleted={() => onRefresh?.()}
      />
    </div>
  );
}

const fetchOverview = () => getLibraryOverview();
const fetchHealth = () => getLibraryHealth();
const fetchStats = () => getLibraryStats();
const fetchPurge = () => getPurgeCandidates();
const fetchStreak = () => getEngagementStreak();
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
  const streak = useDashData(fetchStreak);
  const reviews = useDashData(fetchReviews);
  const runtimeAgg = useDashData(fetchRuntimeAgg);
  const decadeAgg = useDashData(fetchDecadeAgg);
  const genreAgg = useDashData(fetchGenreAgg);
  const countryAgg = useDashData(fetchCountryAgg);
  const languageAgg = useDashData(fetchLanguageAgg);

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
    streak.reload();
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

  const streakCount = streak.data?.streak ?? streak.data?.session_count_30d ?? streak.data?.count ?? streak.data?.sessions ?? 0;

  const purgeCandidates = Array.isArray(purge.data)
    ? purge.data
    : purge.data?.candidates ?? purge.data?.items ?? [];
  const purgeStale = Boolean(purge.data && !Array.isArray(purge.data) && purge.data.stale);
  const purgeGeneratedAt = Array.isArray(purge.data) ? null : purge.data?.generated_at ?? null;

  const recentReviews = Array.isArray(reviews.data)
    ? reviews.data
    : reviews.data?.reviews ?? reviews.data?.items ?? [];

  return (
    <div className="dash-page" data-testid="dashboard-page">
      <header className="dash-header">
        <div>
          <p className="eyebrow">Owner Dashboard</p>
          <h2 className="dash-title">Library Intelligence</h2>
        </div>
        <button type="button" className="ghost" onClick={refreshAll}>
          Refresh
        </button>
      </header>

      {/* ─── At-a-glance owner health hero (M4) ─── */}
      <OwnerHealthHero health={hlth} streak={streak.data} />

      {/* ─── Weekly in-app digest (M4) ─── */}
      <WeeklyDigestPanel />

      {/* ─── One-click grooming rerun + safe undo (M4) ─── */}
      <GroomingUndoPanel onChanged={purge.reload} />

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
      <h2 className="dash-section-title">Curator knowledge</h2>
      <KnowledgeCoverageCard variant="panel" />

      {/* ─── Panel 2: Health & Engagement ─── */}
      <h2 className="dash-section-title">Health &amp; Engagement</h2>
      <div className="dash-grid">
        <Panel title="Unwatched" loading={health.loading} error={health.error}>
          <Gauge value={unwatchedPct} label="Unwatched titles" />
        </Panel>

        <Panel title="Stale Adds" loading={health.loading} error={health.error}>
          <StatCard
            value={staleAdds}
            label="Stale titles"
            detail="Added 90+ days ago, never watched"
          />
        </Panel>

        <Panel title="Rating Coverage" loading={health.loading} error={health.error}>
          <Gauge value={ratingCoverage} label="Watched titles rated" invert />
        </Panel>

        <Panel title="Curator Streak" loading={streak.loading} error={streak.error}>
          <StatCard
            value={streakCount}
            label="Sessions in 30 days"
            accent="var(--accent)"
          />
        </Panel>
      </div>

      {/* ─── Panel 3: Storage Intelligence ─── */}
      <h2 className="dash-section-title">Storage Intelligence</h2>
      <Panel title="Purge Candidates" loading={purge.loading} error={purge.error}>
        <PurgeTable
          candidates={purgeCandidates}
          onRefresh={purge.reload}
          stale={purgeStale}
          generatedAt={purgeGeneratedAt}
          onRefreshNow={handlePurgeRefreshNow}
        />
      </Panel>

      {/* ─── Panel 4: Taste Profile ─── */}
      <h2 className="dash-section-title">Taste Profile</h2>
      <Panel title="Recent Preference Signals" loading={reviews.loading} error={reviews.error}>
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
          <p className="dash-empty">No recent preference signals.</p>
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

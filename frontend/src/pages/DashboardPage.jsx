import { useCallback, useEffect, useState } from "react";
import {
  getLibraryOverview,
  getLibraryAggregate,
  getLibraryHealth,
  getLibraryStats,
  getPurgeCandidates,
  getTvProgress,
  getEngagementStreak,
  listReviews,
} from "../api/client";
import BarChart from "../components/charts/BarChart";
import DonutChart from "../components/charts/DonutChart";
import Gauge from "../components/charts/Gauge";
import ProgressBar from "../components/charts/ProgressBar";
import { buildRuntimeBuckets, sortPurgeCandidates } from "../lib/dashboardCharts.js";

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

function PurgeTable({ candidates }) {
  const [sortKey, setSortKey] = useState("purge_score");
  const [sortDir, setSortDir] = useState("desc");
  const sorted = sortPurgeCandidates(candidates, sortKey, sortDir);

  function handleSort(key) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  const arrow = (key) => (sortKey === key ? (sortDir === "asc" ? " ↑" : " ↓") : "");

  if (!sorted.length) return <p className="dash-empty">No purge candidates found.</p>;

  return (
    <div className="dash-table-wrap">
      <table className="dash-table">
        <thead>
          <tr>
            <th onClick={() => handleSort("title")}>Title{arrow("title")}</th>
            <th onClick={() => handleSort("file_size")}>Size{arrow("file_size")}</th>
            <th onClick={() => handleSort("last_watched")}>Last Watched{arrow("last_watched")}</th>
            <th onClick={() => handleSort("taste_match")}>Taste %{arrow("taste_match")}</th>
            <th onClick={() => handleSort("purge_score")}>Score{arrow("purge_score")}</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {sorted.slice(0, 20).map((c, i) => (
            <tr key={c.title + i}>
              <td className="dash-table-title">{c.title}</td>
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
  );
}

const fetchOverview = () => getLibraryOverview();
const fetchHealth = () => getLibraryHealth();
const fetchStats = () => getLibraryStats();
const fetchPurge = () => getPurgeCandidates();
const fetchTv = () => getTvProgress();
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
  const tv = useDashData(fetchTv);
  const streak = useDashData(fetchStreak);
  const reviews = useDashData(fetchReviews);
  const runtimeAgg = useDashData(fetchRuntimeAgg);
  const decadeAgg = useDashData(fetchDecadeAgg);
  const genreAgg = useDashData(fetchGenreAgg);
  const countryAgg = useDashData(fetchCountryAgg);
  const languageAgg = useDashData(fetchLanguageAgg);

  function refreshAll() {
    overview.reload();
    health.reload();
    stats.reload();
    purge.reload();
    tv.reload();
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

  const streakCount = streak.data?.streak ?? streak.data?.count ?? streak.data?.sessions ?? 0;

  const tvShows = Array.isArray(tv.data)
    ? tv.data
    : tv.data?.shows ?? tv.data?.progress ?? [];
  const topTv = tvShows.slice(0, 5);

  const purgeCandidates = Array.isArray(purge.data)
    ? purge.data
    : purge.data?.candidates ?? [];

  const recentReviews = Array.isArray(reviews.data)
    ? reviews.data
    : reviews.data?.reviews ?? [];

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

        <Panel title="TV Completion" loading={tv.loading} error={tv.error}>
          {topTv.length ? (
            <div className="dash-tv-progress">
              {topTv.map((show) => (
                <ProgressBar
                  key={show.title || show.name || show.show_title}
                  value={show.completion ?? show.progress ?? 0}
                  label={show.title || show.name || show.show_title || "Unknown"}
                  detail={show.detail || (show.seasons_watched != null
                    ? `${show.seasons_watched}/${show.seasons_total} seasons`
                    : undefined)}
                />
              ))}
            </div>
          ) : (
            <p className="dash-empty">No in-progress shows.</p>
          )}
        </Panel>
      </div>

      {/* ─── Panel 3: Storage Intelligence ─── */}
      <h2 className="dash-section-title">Storage Intelligence</h2>
      <Panel title="Purge Candidates" loading={purge.loading} error={purge.error}>
        <PurgeTable candidates={purgeCandidates} />
      </Panel>

      {/* ─── Panel 4: Taste Profile ─── */}
      <h2 className="dash-section-title">Taste Profile</h2>
      <Panel title="Recent Preference Signals" loading={reviews.loading} error={reviews.error}>
        {recentReviews.length ? (
          <ul className="dash-timeline">
            {recentReviews.slice(0, 10).map((r, i) => (
              <li key={r.id ?? i} className="dash-timeline-item">
                <span className="dash-timeline-icon">
                  {r.rating ? "★" : r.dismissed ? "✕" : "♥"}
                </span>
                <div className="dash-timeline-body">
                  <strong>{r.title || r.media_title || "Untitled"}</strong>
                  {r.rating ? (
                    <span className="dash-timeline-meta">{r.rating}/10</span>
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
            ))}
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
  const arr = Array.isArray(raw) ? raw : raw.groups ?? raw.data ?? raw.results ?? [];
  return arr.map((d) => ({
    label: d.label ?? d.group ?? d.name ?? d.decade ?? d.key ?? String(d.value ?? ""),
    value: d.count ?? d.value ?? d.total ?? 0,
  }));
}

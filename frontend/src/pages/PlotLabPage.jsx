import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  getLibraryMotifs,
  getLibraryNeighbors,
  queryLibrary,
} from "../api/client";
import BackLink from "../components/BackLink";
import LibraryMediaCard from "../components/LibraryMediaCard";
import OwnerEmptyStateCta from "../components/OwnerEmptyStateCta";
import RecommendModal from "../components/RecommendModal";
import { useAuthGate } from "../components/UserMenu";
import AppShell from "../layouts/AppShell";
import { ROUTES } from "../lib/browseLinks.js";
import {
  DEFAULT_PLOT_LAB_PAGE_SIZE,
  DEFAULT_PLOT_MATCH_MODE,
  PLOT_LAB_MOTIF_CATALOG_LIMIT,
  PLOT_LAB_PAGE_SIZES,
  buildMotifQueryParams,
  feedPaginationSummary,
  normalizeFeed,
  normalizeMediaTypeFilter,
  normalizeMotifFacets,
  normalizePageSize,
  normalizePlotMatchMode,
  resolveMotifWhy,
  toggleMotifSelection,
} from "../lib/exploreFeeds.js";

const MEDIA_TABS = [
  { id: "all", label: "All", mediaType: null },
  { id: "movie", label: "Movies", mediaType: "movie" },
  { id: "show", label: "TV Shows", mediaType: "show" },
];

function FeedRail({ testId, items, loading }) {
  if (loading) {
    return <p className="status status-secondary">Loading…</p>;
  }
  if (!items?.length) return null;
  return (
    <div className="explore-poster-rail" data-testid={testId}>
      {items.map((item) => (
        <LibraryMediaCard
          key={item.id || item.rating_key || item.title}
          item={item}
          showRecommend={false}
        />
      ))}
    </div>
  );
}

function MotifWallPagination({ summary, pageSize, onPageChange, onPageSizeChange }) {
  if (!summary.total && !summary.returned) return null;
  const from = summary.total ? summary.offset + 1 : 0;
  const to = summary.offset + summary.returned;
  return (
    <div className="explore-section-pagination plot-lab-pagination" data-testid="plot-lab-pagination">
      <p className="explore-section-pagination-summary" data-testid="plot-lab-page-summary">
        Showing {from}–{to} of {summary.total}
        {summary.pageCount > 1 ? ` · Page ${summary.page} of ${summary.pageCount}` : ""}
      </p>
      <div className="explore-section-pagination-controls">
        <label className="explore-section-page-size">
          <span>Per page</span>
          <select
            value={pageSize}
            data-testid="plot-lab-page-size"
            onChange={(event) => onPageSizeChange(Number(event.target.value))}
          >
            {PLOT_LAB_PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
        <div className="explore-section-page-nav">
          <button
            type="button"
            className="ghost"
            data-testid="plot-lab-prev"
            disabled={!summary.hasPrev}
            onClick={() => onPageChange(summary.page - 1)}
          >
            Previous
          </button>
          <button
            type="button"
            className="ghost"
            data-testid="plot-lab-next"
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

export default function PlotLabPage() {
  const { isOwner, multiUserEnabled } = useAuthGate();
  const [motifs, setMotifs] = useState([]);
  const [motifsNote, setMotifsNote] = useState("");
  const [motifsLoading, setMotifsLoading] = useState(true);
  const [selectedMotifs, setSelectedMotifs] = useState([]);
  const [mediaType, setMediaType] = useState(null);
  const [plotMatchMode, setPlotMatchMode] = useState(DEFAULT_PLOT_MATCH_MODE);
  const [pageSize, setPageSize] = useState(DEFAULT_PLOT_LAB_PAGE_SIZE);
  const [offset, setOffset] = useState(0);
  const [motifWall, setMotifWall] = useState({
    loading: false,
    items: [],
    note: null,
    error: "",
    payload: null,
  });
  const [seed, setSeed] = useState(null);
  const [seedQuery, setSeedQuery] = useState("");
  const [seedHits, setSeedHits] = useState([]);
  const [neighbors, setNeighbors] = useState({ loading: false, items: [], note: null, error: "" });
  const [recommendItem, setRecommendItem] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setMotifsLoading(true);
    getLibraryMotifs({ limit: PLOT_LAB_MOTIF_CATALOG_LIMIT })
      .then((data) => {
        if (cancelled) return;
        const facets = normalizeMotifFacets(data);
        setMotifs(facets);
        setMotifsNote(
          facets.length
            ? ""
            : "No plot motifs yet — summary_motifs idle task has not populated facets.",
        );
        setMotifsLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setMotifs([]);
        setMotifsNote(err.message || "Could not load motifs.");
        setMotifsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedMotifs.length) {
      setMotifWall({ loading: false, items: [], note: null, error: "", payload: null });
      return undefined;
    }
    let cancelled = false;
    setMotifWall((prev) => ({ ...prev, loading: true, error: "" }));
    const params = buildMotifQueryParams(selectedMotifs, {
      limit: pageSize,
      offset,
      mediaType,
      plotMatchMode,
    });
    queryLibrary(Object.fromEntries(params.entries()))
      .then((data) => {
        if (cancelled) return;
        const items = Array.isArray(data?.items) ? data.items : [];
        setMotifWall({
          loading: false,
          items,
          note: items.length ? null : "No titles match the selected plot signals.",
          error: "",
          payload: data,
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setMotifWall({
          loading: false,
          items: [],
          note: null,
          error: err.message || "Could not filter by motifs.",
          payload: null,
        });
      });
    return () => {
      cancelled = true;
    };
  }, [selectedMotifs, mediaType, pageSize, offset, plotMatchMode]);

  useEffect(() => {
    if (!seed?.id) {
      setNeighbors({ loading: false, items: [], note: null, error: "" });
      return undefined;
    }
    let cancelled = false;
    setNeighbors({ loading: true, items: [], note: null, error: "" });
    getLibraryNeighbors(seed.id, { mode: "surprising", limit: 12 })
      .then((data) => {
        if (cancelled) return;
        const normalized = normalizeFeed(data, {
          fallbackNote: "Empty — plot_neighbors cache not built yet for this title.",
        });
        setNeighbors({
          loading: false,
          items: normalized.items,
          note: normalized.note,
          error: "",
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setNeighbors({
          loading: false,
          items: [],
          note: null,
          error: err.message || "Could not load surprising neighbors.",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [seed]);

  useEffect(() => {
    const q = seedQuery.trim();
    if (q.length < 2) {
      setSeedHits([]);
      return undefined;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      const filters = { query: q, limit: 6 };
      const media = normalizeMediaTypeFilter(mediaType);
      if (media) filters.media_type = media;
      queryLibrary(filters)
        .then((data) => {
          if (cancelled) return;
          setSeedHits(Array.isArray(data?.items) ? data.items : []);
        })
        .catch(() => {
          if (!cancelled) setSeedHits([]);
        });
    }, 220);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [seedQuery, mediaType]);

  const wallSummary = useMemo(
    () =>
      feedPaginationSummary({
        ...(motifWall.payload || {}),
        items: motifWall.items,
        total: motifWall.payload?.total_matched ?? motifWall.payload?.total ?? 0,
        offset,
        limit: pageSize,
      }),
    [motifWall.items, motifWall.payload, offset, pageSize],
  );

  const activeMediaTab =
    MEDIA_TABS.find((tab) => tab.mediaType === mediaType)?.id || "all";

  function handleToggleMotif(value) {
    setSelectedMotifs((prev) => toggleMotifSelection(prev, value));
    setOffset(0);
  }

  function handleMediaTab(nextType) {
    setMediaType(normalizeMediaTypeFilter(nextType));
    setOffset(0);
  }

  function handlePlotMatchMode(nextMode) {
    setPlotMatchMode(normalizePlotMatchMode(nextMode));
    setOffset(0);
  }

  function handlePageSizeChange(nextSize) {
    setPageSize(normalizePageSize(nextSize, PLOT_LAB_PAGE_SIZES));
    setOffset(0);
  }

  function handlePageChange(page) {
    const nextPage = Math.max(1, page);
    setOffset((nextPage - 1) * pageSize);
  }

  function handleSeed(item) {
    setSeed(item);
    setSeedQuery(item.title || "");
    setSeedHits([]);
  }

  return (
    <AppShell
      className="app-root explore-page plot-lab-page"
      testId="plot-lab-page"
      title="Plot Lab"
      eyebrow="Motifs, poster walls, and surprising narrative neighbors"
      actions={<BackLink fallbackTo={ROUTES.explore} testId="plot-lab-back" />}
    >
      <main className="explore-main">
        {motifsLoading ? (
          <p className="status status-secondary">Loading motifs…</p>
        ) : motifsNote && !motifs.length ? (
          <div className="explore-empty-block">
            <p className="explore-empty status status-secondary">{motifsNote}</p>
            <OwnerEmptyStateCta note={motifsNote} isOwner={isOwner} />
          </div>
        ) : null}

        {motifs.length ? (
          <>
            <div
              className="explore-media-tabs plot-lab-media-tabs"
              role="tablist"
              aria-label="Media type"
              data-testid="plot-lab-media-tabs"
            >
              {MEDIA_TABS.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={activeMediaTab === tab.id}
                  className={`explore-media-tab${activeMediaTab === tab.id ? " is-active" : ""}`}
                  data-testid={`plot-lab-tab-${tab.id}`}
                  onClick={() => handleMediaTab(tab.mediaType)}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <div
              className="explore-motif-chips explore-motif-chips-scroll"
              data-testid="explore-motif-chips"
            >
              {motifs.map((facet) => {
                const active = selectedMotifs.includes(facet.value);
                return (
                  <button
                    key={facet.value}
                    type="button"
                    className={`explore-motif-chip${active ? " is-active" : ""}`}
                    data-testid="explore-motif-chip"
                    aria-pressed={active}
                    onClick={() => handleToggleMotif(facet.value)}
                  >
                    {facet.value}
                    {facet.count ? <span className="explore-motif-count">{facet.count}</span> : null}
                  </button>
                );
              })}
            </div>
          </>
        ) : null}

        {selectedMotifs.length ? (
          <div className="explore-plot-lab-wall" data-testid="explore-motif-wall">
            <h3 className="explore-plot-lab-heading">Motif wall</h3>
            <div
              className="explore-media-tabs plot-lab-match-mode"
              role="tablist"
              aria-label="Plot match mode"
              data-testid="plot-lab-match-mode"
            >
              <button
                type="button"
                role="tab"
                aria-selected={plotMatchMode === "hybrid"}
                className={`explore-media-tab${plotMatchMode === "hybrid" ? " is-active" : ""}`}
                data-testid="plot-lab-mode-hybrid"
                onClick={() => handlePlotMatchMode("hybrid")}
              >
                Multi-signal
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={plotMatchMode === "motifs"}
                className={`explore-media-tab${plotMatchMode === "motifs" ? " is-active" : ""}`}
                data-testid="plot-lab-mode-motifs"
                onClick={() => handlePlotMatchMode("motifs")}
              >
                Motifs only
              </button>
            </div>
            {selectedMotifs.length > 1 ? (
              <p className="explore-section-subtitle" data-testid="plot-lab-intersection-hint">
                {plotMatchMode === "motifs"
                  ? `Titles matching all selected motifs (${selectedMotifs.join(" · ")}).`
                  : `Titles matching all selected signals across motifs, keywords, and plot text (${selectedMotifs.join(" · ")}).`}{" "}
                Tap Why? on a poster for which layer matched.
              </p>
            ) : null}
            {motifWall.error || motifWall.note ? (
              <p className="explore-empty status status-secondary">
                {motifWall.error || motifWall.note}
              </p>
            ) : null}
            {motifWall.loading ? (
              <p className="status status-secondary">Filtering titles…</p>
            ) : motifWall.items.length ? (
              <>
                <MotifWallPagination
                  summary={wallSummary}
                  pageSize={pageSize}
                  onPageChange={handlePageChange}
                  onPageSizeChange={handlePageSizeChange}
                />
                <div className="explore-poster-wall">
                  {motifWall.items.map((item) => (
                    <LibraryMediaCard
                      key={item.id || item.rating_key || item.title}
                      item={item}
                      onSeed={handleSeed}
                      showRecommend={multiUserEnabled}
                      onRecommend={multiUserEnabled ? setRecommendItem : undefined}
                      motifWhy={resolveMotifWhy(item, selectedMotifs)}
                    />
                  ))}
                </div>
                <MotifWallPagination
                  summary={wallSummary}
                  pageSize={pageSize}
                  onPageChange={handlePageChange}
                  onPageSizeChange={handlePageSizeChange}
                />
              </>
            ) : null}
          </div>
        ) : null}

        <div className="explore-seed-panel" data-testid="explore-seed-panel">
          <h3 className="explore-plot-lab-heading">Surprising neighbors</h3>
          <p className="explore-section-subtitle">
            Pick a seed title to surface narrative oddballs from the plot cache.
          </p>
          <label className="explore-seed-label" htmlFor="explore-seed-input">
            Seed title
          </label>
          <input
            id="explore-seed-input"
            className="explore-seed-input"
            data-testid="explore-seed-input"
            type="search"
            placeholder="Search your library…"
            value={seedQuery}
            onChange={(e) => setSeedQuery(e.target.value)}
            autoComplete="off"
          />
          {seedHits.length ? (
            <ul className="explore-seed-hits" data-testid="explore-seed-hits">
              {seedHits.map((item) => (
                <li key={item.id || item.rating_key || item.title}>
                  <button type="button" onClick={() => handleSeed(item)}>
                    {item.title}
                    {item.year ? ` (${item.year})` : ""}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          {seed ? (
            <p className="explore-seed-active" data-testid="explore-seed-active">
              Seed: <strong>{seed.title}</strong>
              {seed.year ? ` (${seed.year})` : ""}
            </p>
          ) : null}
          {neighbors.error || neighbors.note ? (
            <div className="explore-empty-block">
              <p className="explore-empty status status-secondary">
                {neighbors.error || neighbors.note}
              </p>
              {!neighbors.error && !neighbors.items.length ? (
                <OwnerEmptyStateCta note={neighbors.note} isOwner={isOwner} />
              ) : null}
            </div>
          ) : null}
          <FeedRail
            testId="explore-neighbors-rail"
            items={neighbors.items}
            loading={neighbors.loading}
          />
        </div>

        <p className="explore-hub-link-row">
          <Link to={ROUTES.explore} className="app-topbar-link">
            Explore hub
          </Link>
          <Link to={ROUTES.tags} className="app-topbar-link">
            Tag search
          </Link>
        </p>
      </main>

      <RecommendModal
        item={recommendItem}
        open={Boolean(recommendItem)}
        onClose={() => setRecommendItem(null)}
      />
    </AppShell>
  );
}

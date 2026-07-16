import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  getExploreFeedRecentReleases,
  getExploreFeedRecentlyAdded,
} from "../api/client";
import BackLink from "../components/BackLink.jsx";
import LibraryMediaCard from "../components/LibraryMediaCard.jsx";
import { exploreSectionPath } from "../lib/browseLinks.js";
import { ROUTES } from "../lib/backNav.js";
import {
  EXPLORE_PAGE_SIZES,
  buildExploreSectionQuery,
  feedPaginationSummary,
  getExploreSectionConfig,
  normalizeFeed,
  parseExploreSectionQuery,
} from "../lib/exploreFeeds.js";

const FEED_LOADERS = {
  "recently-added": getExploreFeedRecentlyAdded,
  "recent-releases": getExploreFeedRecentReleases,
};

const MEDIA_TABS = [
  { id: "all", label: "All", mediaType: null },
  { id: "movie", label: "Movies", mediaType: "movie" },
  { id: "show", label: "TV", mediaType: "show" },
];

function SectionPagination({ summary, onPageChange, onPageSizeChange, pageSize }) {
  if (!summary.total && !summary.returned) return null;
  return (
    <div className="explore-section-pagination" data-testid="explore-section-pagination">
      <p className="explore-section-pagination-summary" data-testid="explore-section-page-summary">
        Page {summary.page} of {summary.pageCount}
        {summary.total ? ` · ${summary.total} titles` : ""}
      </p>
      <div className="explore-section-pagination-controls">
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
        <div className="explore-section-page-nav">
          <button
            type="button"
            className="ghost"
            data-testid="explore-section-prev"
            disabled={!summary.hasPrev}
            onClick={() => onPageChange(summary.page - 1)}
          >
            Previous
          </button>
          <button
            type="button"
            className="ghost"
            data-testid="explore-section-next"
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
  const config = getExploreSectionConfig(sectionId);
  const query = useMemo(() => parseExploreSectionQuery(searchParams), [searchParams]);
  const [state, setState] = useState({
    loading: true,
    items: [],
    note: null,
    error: "",
    payload: null,
  });

  useEffect(() => {
    if (!config) return undefined;
    const loader = FEED_LOADERS[config.feed];
    if (!loader) return undefined;
    let cancelled = false;
    setState((prev) => ({ ...prev, loading: true, error: "" }));
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

  const summary = useMemo(
    () => feedPaginationSummary(state.payload || { items: state.items, total: state.items.length }),
    [state.items, state.payload],
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

  if (!config) {
    return (
      <div className="app-root explore-section-page" data-testid="explore-section-page">
        <header className="browse-page-header">
          <BackLink fallbackTo={ROUTES.explore} testId="explore-section-back" />
        </header>
        <p className="error" data-testid="explore-section-unknown">
          Unknown Explore section.
        </p>
        <Link to={ROUTES.explore} className="app-topbar-link">
          Return to Explore
        </Link>
      </div>
    );
  }

  const activeTab =
    MEDIA_TABS.find((tab) => tab.mediaType === query.mediaType)?.id || "all";

  return (
    <div className="app-root explore-section-page" data-testid="explore-section-page">
      <header className="browse-page-header">
        <BackLink fallbackTo={ROUTES.explore} testId="explore-section-back" />
        <Link to={ROUTES.explore} className="app-topbar-link" data-testid="explore-section-hub-link">
          Explore hub
        </Link>
      </header>

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

      <SectionPagination
        summary={summary}
        pageSize={query.limit}
        onPageChange={handlePageChange}
        onPageSizeChange={handlePageSizeChange}
      />

      <section className="explore-section-results" data-testid="explore-section-results">
        {state.loading ? <p className="status status-secondary">Loading…</p> : null}
        {state.error ? <p className="error">{state.error}</p> : null}
        {!state.loading && !state.error && !state.items.length ? (
          <p className="explore-empty status status-secondary" data-testid="explore-section-empty">
            {state.note || "No titles in this section yet."}
          </p>
        ) : null}
        {state.items.length ? (
          <div className="explore-poster-wall">
            {state.items.map((item) => (
              <LibraryMediaCard
                key={item.id || item.rating_key || `${item.media_type}-${item.tmdb_id || item.title}`}
                item={item}
              />
            ))}
          </div>
        ) : null}
      </section>

      <SectionPagination
        summary={summary}
        pageSize={query.limit}
        onPageChange={handlePageChange}
        onPageSizeChange={handlePageSizeChange}
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
    </div>
  );
}

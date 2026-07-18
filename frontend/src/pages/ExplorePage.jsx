import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  getExploreFeedOnThisDay,
  getExploreFeedRecentReleases,
  getExploreFeedRecentlyAdded,
  getExploreFeedRevisitThese,
  getLibraryHealth,
  getLibraryOverview,
  queryLibrary,
} from "../api/client";
import BackLink from "../components/BackLink";
import KnowledgeCoverageCard from "../components/KnowledgeCoverageCard";
import LibraryMediaCard from "../components/LibraryMediaCard";
import MediaBrowseControls from "../components/MediaBrowseControls";
import MediaBrowseResults from "../components/MediaBrowseResults";
import OwnerEmptyStateCta from "../components/OwnerEmptyStateCta";
import RecommendModal from "../components/RecommendModal";
import { useAuthGate } from "../components/UserMenu";
import AppShell from "../layouts/AppShell";
import { ROUTES, decadeYearRange, exploreSectionPath } from "../lib/browseLinks.js";
import { formatLanguageName } from "../lib/languageNames.js";
import { buildPulseStats, normalizeFeed } from "../lib/exploreFeeds.js";
import {
  buildMediaBrowseParams,
  mediaBrowseRowsToCsv,
  matchesMediaBrowseWatchState,
  parseMediaBrowse,
  queryFiltersFromBrowse,
} from "../lib/mediaBrowse.js";

function ExplorePosterCard({ item, meta, onSeed, seedLabel = "Surprise from this", onRecommend, showRecommend }) {
  return (
    <LibraryMediaCard
      item={item}
      meta={meta}
      onSeed={onSeed}
      seedLabel={seedLabel}
      onRecommend={onRecommend}
      showRecommend={showRecommend}
    />
  );
}

function ExploreSection({
  id,
  title,
  subtitle,
  children,
  empty,
  note,
  titleHref,
  mediaTypeLinks,
  isOwner = false,
}) {
  const message = empty || note || null;
  // Owner task CTAs only for true empties — not informational notes on populated rails.
  const ownerCtaNote = empty || null;
  return (
    <section className="explore-section" data-testid={`explore-section-${id}`}>
      <header className="explore-section-header">
        <div>
          <div className="explore-section-title-row">
            <h2>
              {titleHref ? (
                <Link
                  to={titleHref}
                  className="explore-section-title-link"
                  data-testid={`explore-section-link-${id}`}
                >
                  {title}
                </Link>
              ) : (
                title
              )}
            </h2>
            {mediaTypeLinks?.length ? (
              <nav className="explore-section-type-links" aria-label={`${title} by type`}>
                {mediaTypeLinks.map((link) => (
                  <Link
                    key={link.mediaType}
                    to={link.href}
                    className="explore-section-type-link"
                    data-testid={`explore-section-type-${id}-${link.mediaType}`}
                  >
                    {link.label}
                  </Link>
                ))}
              </nav>
            ) : null}
          </div>
          {subtitle ? <p className="explore-section-subtitle">{subtitle}</p> : null}
        </div>
      </header>
      {message ? (
        <div className="explore-empty-block">
          <p className="explore-empty status status-secondary">{message}</p>
          <OwnerEmptyStateCta note={ownerCtaNote} isOwner={isOwner} />
        </div>
      ) : null}
      {children}
    </section>
  );
}

function FeedRail({ testId, items, loading, cardMeta, onSeed, onRecommend, showRecommend }) {
  if (loading) {
    return <p className="status status-secondary">Loading…</p>;
  }
  if (!items.length) return null;
  return (
    <div className="explore-card-rail" data-testid={testId}>
      {items.map((item) => (
        <ExplorePosterCard
          key={item.id || item.rating_key || `${item.media_type}-${item.tmdb_id || item.title}`}
          item={item}
          meta={cardMeta ? cardMeta(item) : item.anniversary_context || null}
          onSeed={onSeed}
          onRecommend={onRecommend}
          showRecommend={showRecommend}
        />
      ))}
    </div>
  );
}

function matchesFacetBrowse(item, browse) {
  if (browse.year && String(item?.year || "") !== String(browse.year)) return false;
  return matchesMediaBrowseWatchState(item, browse.watch_state);
}

function useFeed(loader, deps = []) {
  const [state, setState] = useState({ loading: true, items: [], note: null, error: "" });
  useEffect(() => {
    let cancelled = false;
    setState((prev) => ({ ...prev, loading: true, error: "" }));
    loader()
      .then((payload) => {
        if (cancelled) return;
        const normalized = normalizeFeed(payload);
        setState({
          loading: false,
          items: normalized.items,
          note: normalized.note,
          error: "",
          meta: normalized.meta,
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setState({
          loading: false,
          items: [],
          note: null,
          error: err.message || "Could not load this feed.",
          meta: {},
        });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

export default function ExplorePage() {
  const { isOwner, multiUserEnabled } = useAuthGate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [recommendItem, setRecommendItem] = useState(null);
  const [facetColumns, setFacetColumns] = useState(null);
  const recentlyAdded = useFeed(() => getExploreFeedRecentlyAdded({ limit: 12, days: 30 }), []);
  const recentReleases = useFeed(() => getExploreFeedRecentReleases({ limit: 12, days: 90 }), []);
  const revisitThese = useFeed(() => getExploreFeedRevisitThese({ limit: 20, idleDays: 60 }), []);
  const onThisDay = useFeed(() => getExploreFeedOnThisDay({ limit: 12 }), []);
  const facetBrowse = useMemo(() => parseMediaBrowse(searchParams), [searchParams]);

  const [pulse, setPulse] = useState({ loading: true, stats: [], error: "" });
  const [facetWall, setFacetWall] = useState({ loading: false, items: [], note: null, error: "", label: "" });

  useEffect(() => {
    let cancelled = false;
    Promise.all([getLibraryOverview(), getLibraryHealth()])
      .then(([overview, health]) => {
        if (cancelled) return;
        setPulse({ loading: false, stats: buildPulseStats(overview, health), error: "" });
      })
      .catch((err) => {
        if (cancelled) return;
        setPulse({
          loading: false,
          stats: [],
          error: err.message || "Could not load library pulse.",
        });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const genre = String(searchParams.get("genre") || "").trim();
    const cast = String(searchParams.get("cast") || "").trim();
    const directors = String(searchParams.get("directors") || "").trim();
    const decade = String(searchParams.get("decade") || "").trim();
    const language = String(searchParams.get("language") || "").trim();
    const country = String(searchParams.get("country") || "").trim();
    if (!genre && !cast && !directors && !decade && !language && !country) {
      setFacetWall({ loading: false, items: [], note: null, error: "", label: "" });
      return undefined;
    }
    const filters = queryFiltersFromBrowse(facetBrowse);
    let label = "";
    if (genre) {
      filters.genres = [...new Set([genre, ...(facetBrowse.genres || [])])];
      label = `Genre: ${genre}`;
    } else if (cast) {
      filters.cast = [cast];
      label = `Cast: ${cast}`;
    } else if (directors) {
      filters.directors = [directors];
      label = `Director: ${directors}`;
    } else if (decade) {
      const range = decadeYearRange(decade);
      if (range) {
        filters.year_from = range.year_from;
        filters.year_to = range.year_to;
      }
      label = `Decade: ${decade}`;
    } else if (language) {
      filters.original_language = language.toLowerCase();
      label = `Language: ${formatLanguageName(language)}`;
    } else if (country) {
      filters.countries = [country];
      label = `Country: ${country}`;
    }
    let cancelled = false;
    setFacetWall({ loading: true, items: [], note: null, error: "", label });
    queryLibrary(filters)
      .then((data) => {
        if (cancelled) return;
        const items = Array.isArray(data?.items) ? data.items : [];
        setFacetWall({
          loading: false,
          items,
          note: items.length ? null : `No library titles match ${label.toLowerCase()}.`,
          error: "",
          label,
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setFacetWall({
          loading: false,
          items: [],
          note: null,
          error: err.message || "Could not load filtered titles.",
          label,
        });
      });
    return () => {
      cancelled = true;
    };
  }, [facetBrowse, searchParams]);

  const otdSubtitle = useMemo(() => {
    const mode = onThisDay.meta?.mode;
    if (mode === "calendar") return "Release anniversaries sharing today’s date";
    if (mode === "milestone_fallback") return "Milestone-year picks from your shelves";
    return "Anniversary picks from your shelves";
  }, [onThisDay.meta?.mode]);

  const recommendProps = multiUserEnabled
    ? { showRecommend: true, onRecommend: setRecommendItem }
    : { showRecommend: false };

  const facetFilterOptions = useMemo(() => ({
    years: [...new Set(facetWall.items.map((item) => item.year).filter(Boolean))].sort((a, b) => b - a),
    genres: [...new Set(facetWall.items.flatMap((item) => item.genres || []).filter(Boolean))].sort(),
  }), [facetWall.items]);
  const facetItems = useMemo(
    () => facetWall.items.filter((item) => matchesFacetBrowse(item, facetBrowse)),
    [facetWall.items, facetBrowse],
  );

  function handleFacetBrowseChange(patch) {
    const params = new URLSearchParams(searchParams);
    for (const key of ["view", "sort", "sort_dir", "limit", "offset", "media_type", "watch_state", "year", "genres", "keywords"]) {
      params.delete(key);
    }
    for (const [key, value] of buildMediaBrowseParams(facetBrowse, patch)) {
      params.set(key, value);
    }
    setSearchParams(params, { replace: true });
  }

  function exportFacetPage(columns) {
    const blob = new Blob([mediaBrowseRowsToCsv(facetItems, columns)], { type: "text/csv;charset=utf-8" });
    const href = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = href;
    link.download = "explore-facet.csv";
    link.click();
    URL.revokeObjectURL(href);
  }

  return (
    <AppShell
      className="app-root explore-page"
      testId="explore-page"
      title="Explore"
      eyebrow="Browse your cinema"
      actions={<BackLink fallbackTo={ROUTES.chat} testId="explore-back-chat" label="Back to chat" />}
    >
      <main className="explore-main">
        <section className="explore-hub-links" data-testid="explore-hub-links">
          <Link to={ROUTES.plotLab} className="explore-hub-card" data-testid="explore-hub-plot-lab">
            <h2>Plot Lab</h2>
            <p>Motifs, poster walls, and surprising narrative neighbors</p>
          </Link>
          <Link to={ROUTES.tags} className="explore-hub-card" data-testid="explore-hub-tags">
            <h2>Tag search</h2>
            <p>Find keyword tags across your full library index</p>
          </Link>
        </section>

        <KnowledgeCoverageCard variant="strip" />

        <ExploreSection
          id="recently-added"
          title="Recently Added"
          subtitle="Fresh arrivals from the last 30 days"
          titleHref={exploreSectionPath("recently-added")}
          isOwner={isOwner}
          mediaTypeLinks={[
            {
              mediaType: "movie",
              label: "Movies",
              href: exploreSectionPath("recently-added", { mediaType: "movie" }),
            },
            {
              mediaType: "show",
              label: "TV",
              href: exploreSectionPath("recently-added", { mediaType: "show" }),
            },
          ]}
          empty={
            recentlyAdded.error ||
            (!recentlyAdded.loading && !recentlyAdded.items.length ? recentlyAdded.note : null)
          }
        >
          <FeedRail
            testId="explore-recently-added-rail"
            items={recentlyAdded.items}
            loading={recentlyAdded.loading}
            {...recommendProps}
          />
        </ExploreSection>

        <ExploreSection
          id="recent-releases"
          title="Recent Releases"
          subtitle="Library titles released in the last 90 days"
          titleHref={exploreSectionPath("recent-releases")}
          isOwner={isOwner}
          mediaTypeLinks={[
            {
              mediaType: "movie",
              label: "Movies",
              href: exploreSectionPath("recent-releases", { mediaType: "movie" }),
            },
            {
              mediaType: "show",
              label: "TV",
              href: exploreSectionPath("recent-releases", { mediaType: "show" }),
            },
          ]}
          empty={
            recentReleases.error ||
            (!recentReleases.loading && !recentReleases.items.length ? recentReleases.note : null)
          }
        >
          <FeedRail
            testId="explore-recent-releases-rail"
            items={recentReleases.items}
            loading={recentReleases.loading}
            {...recommendProps}
          />
        </ExploreSection>

        <ExploreSection
          id="revisit-these"
          title="Revisit These"
          subtitle="Partially watched shows you haven’t touched in over two months"
          isOwner={isOwner}
          empty={
            revisitThese.error ||
            (!revisitThese.loading && !revisitThese.items.length ? revisitThese.note : null)
          }
        >
          <FeedRail
            testId="explore-revisit-these-rail"
            items={revisitThese.items}
            loading={revisitThese.loading}
            {...recommendProps}
          />
        </ExploreSection>

        <ExploreSection
          id="library-pulse"
          title="Library Pulse"
          subtitle="A quick read on collection health"
          isOwner={isOwner}
          empty={pulse.error || (!pulse.loading && !pulse.stats.length ? "No overview stats yet." : null)}
        >
          {pulse.loading ? (
            <p className="status status-secondary">Loading pulse…</p>
          ) : pulse.stats.length ? (
            <div className="explore-pulse" data-testid="explore-pulse-grid">
              {pulse.stats
                .filter((stat) => stat.kind === "summary")
                .map((stat) => (
                  <p key={stat.id} className="explore-pulse-summary" data-testid={`explore-pulse-${stat.id}`}>
                    <span className="explore-pulse-summary-value">{stat.value}</span>
                    <span className="explore-pulse-summary-label">{stat.label}</span>
                  </p>
                ))}
              <div className="explore-pulse-grid">
                {pulse.stats
                  .filter((stat) => stat.kind !== "summary")
                  .map((stat) => (
                    <div
                      key={stat.id}
                      className="explore-pulse-media-card"
                      data-testid={`explore-pulse-${stat.id}`}
                    >
                      <div className="explore-pulse-media-header">
                        <span className="explore-pulse-value">{stat.value}</span>
                        <span className="explore-pulse-label">{stat.label}</span>
                      </div>
                      {stat.metrics?.length ? (
                        <dl className="explore-pulse-metrics">
                          {stat.metrics.map((metric) => (
                            <div
                              key={metric.id}
                              className="explore-pulse-metric"
                              data-testid={`explore-pulse-${stat.id}-${metric.id}`}
                              title={metric.detail || undefined}
                            >
                              <dt>{metric.label}</dt>
                              <dd>{metric.value}</dd>
                            </div>
                          ))}
                        </dl>
                      ) : null}
                    </div>
                  ))}
              </div>
            </div>
          ) : null}
        </ExploreSection>

        <ExploreSection
          id="on-this-day"
          title="On This Day"
          subtitle={otdSubtitle}
          isOwner={isOwner}
          empty={onThisDay.error || (!onThisDay.loading && !onThisDay.items.length ? onThisDay.note : null)}
          note={onThisDay.items.length && onThisDay.note && !onThisDay.error ? onThisDay.note : null}
        >
          <FeedRail
            testId="explore-on-this-day-rail"
            items={onThisDay.items}
            loading={onThisDay.loading}
            {...recommendProps}
          />
        </ExploreSection>

        {facetWall.label ? (
          <ExploreSection
            id="facet-filter"
            title={facetWall.label}
            subtitle="Deep-link filter from title detail"
            isOwner={isOwner}
            empty={facetWall.error || facetWall.note}
          >
            {facetWall.loading ? (
              <p className="status status-secondary">Loading titles…</p>
            ) : facetItems.length ? (
              <>
                <div className="explore-section-toolbar" data-testid="explore-facet-toolbar">
                  <MediaBrowseControls
                    state={facetBrowse}
                    onChange={handleFacetBrowseChange}
                    columns={facetColumns}
                    onColumnsChange={setFacetColumns}
                    columnScope="explore-facet"
                    filterOptions={facetFilterOptions}
                    exportItems
                    onExport={exportFacetPage}
                  />
                </div>
                <div data-testid="explore-facet-wall">
                  <MediaBrowseResults
                    state={facetBrowse}
                    items={facetItems}
                    columns={facetColumns || undefined}
                    cardProps={{ testId: "explore-facet-title-card", ...recommendProps }}
                  />
                </div>
              </>
            ) : null}
          </ExploreSection>
        ) : null}
      </main>

      <RecommendModal
        item={recommendItem}
        open={Boolean(recommendItem)}
        onClose={() => setRecommendItem(null)}
      />
    </AppShell>
  );
}

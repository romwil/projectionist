import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  getExploreFeedContinueWatching,
  getExploreFeedDirectorSpotlight,
  getExploreFeedGenreSpotlight,
  getExploreFeedOnThisDay,
  getExploreFeedRecentReleases,
  getExploreFeedRecentlyAdded,
  getExploreFeedRevisitThese,
  getExploreFeedSeasonalSpotlight,
  anniversaryLiveStarter,
  getPickForMeFeed,
  getLibraryHealth,
  getLibraryOverview,
  queryLibrary,
} from "../api/client";
import HelpHint from "../components/HelpHint";
import KnowledgeCoverageCard from "../components/KnowledgeCoverageCard";
import LibrarySearchBar from "../components/LibrarySearchBar.jsx";
import LibraryMediaCard from "../components/LibraryMediaCard";
import MediaBrowseControls from "../components/MediaBrowseControls";
import MediaBrowseResults from "../components/MediaBrowseResults";
import TonightDoubleFeatureHabit from "../components/TonightDoubleFeatureHabit";
import WhatsOnTonightHabit from "../components/WhatsOnTonightHabit";
import OwnerEmptyStateCta from "../components/OwnerEmptyStateCta";
import PosterRailLoader from "../components/PosterRailLoader";
import RecommendModal from "../components/RecommendModal";
import { useAuthGate } from "../components/UserMenu";
import AppShell from "../layouts/AppShell";
import { chatFromRailHref } from "../lib/backNav.js";
import { liveWatchHref } from "../lib/liveChannels.js";
import { ROUTES, decadeYearRange, exploreSectionPath, libraryBrowsePath } from "../lib/browseLinks.js";
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
  helpAnchorId,
  helpTitle = "Learn more in Help",
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
            {helpAnchorId ? (
              <HelpHint
                anchor={helpAnchorId}
                title={helpTitle}
                testId={`explore-section-help-${id}`}
              />
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

function FeedRail({
  testId,
  items,
  loading,
  cardMeta,
  onSeed,
  onRecommend,
  showRecommend,
  chatHref,
  chatLabel = "Chat about these",
}) {
  if (loading) {
    return <PosterRailLoader testId={`${testId}-loader`} />;
  }
  if (!items.length) return null;
  return (
    <div className="explore-rail-wrap">
      {chatHref ? (
        <div className="explore-rail-actions">
          <Link to={chatHref} className="explore-rail-chat-link" data-testid={`${testId}-chat`}>
            {chatLabel}
          </Link>
        </div>
      ) : null}
      <div className="explore-card-rail" data-testid={testId}>
        {items.map((item) => (
          <ExplorePosterCard
            key={item.id || item.rating_key || `${item.media_type}-${item.tmdb_id || item.title}`}
            item={item}
            meta={
              cardMeta
                ? cardMeta(item)
                : item.resume_label || item.anniversary_context || item.why || null
            }
            onSeed={onSeed}
            onRecommend={onRecommend}
            showRecommend={showRecommend}
          />
        ))}
      </div>
    </div>
  );
}

function matchesFacetBrowse(item, browse) {
  if (browse.year && String(item?.year || "") !== String(browse.year)) return false;
  return matchesMediaBrowseWatchState(item, browse.watch_state);
}

function exploreFacetPath(key, value) {
  const params = new URLSearchParams([[key, value]]);
  return `${ROUTES.explore}?${params}`;
}

function useFeed(loader, deps = []) {
  const [state, setState] = useState({ loading: true, items: [], note: null, error: "", meta: {} });
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
          meta: normalized.meta || {},
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
  const { isOwner, multiUserEnabled, isYouth } = useAuthGate();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [recommendItem, setRecommendItem] = useState(null);
  const [facetColumns, setFacetColumns] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const continueWatching = useFeed(() => getExploreFeedContinueWatching({ limit: 12 }), []);
  const pickForMe = useFeed(() => getPickForMeFeed({ limit: 8 }), []);
  const recentlyAdded = useFeed(() => getExploreFeedRecentlyAdded({ limit: 12, days: 30 }), []);
  const recentReleases = useFeed(() => getExploreFeedRecentReleases({ limit: 12, days: 90 }), []);
  const revisitThese = useFeed(() => getExploreFeedRevisitThese({ limit: 20, idleDays: 60 }), []);
  const onThisDay = useFeed(() => getExploreFeedOnThisDay({ limit: 12 }), []);
  const directorSpotlight = useFeed(() => getExploreFeedDirectorSpotlight({ limit: 12 }), []);
  const genreSpotlight = useFeed(() => getExploreFeedGenreSpotlight({ limit: 12 }), []);
  const seasonalSpotlight = useFeed(() => getExploreFeedSeasonalSpotlight({ limit: 12 }), []);
  const facetBrowse = useMemo(() => parseMediaBrowse(searchParams), [searchParams]);

  const [pulse, setPulse] = useState({ loading: true, stats: [], error: "" });
  const [facetWall, setFacetWall] = useState({ loading: false, items: [], note: null, error: "", label: "" });
  const [anniversaryNote, setAnniversaryNote] = useState("");
  const [anniversaryBusy, setAnniversaryBusy] = useState(false);

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

  function handleSearchSubmit(event) {
    event.preventDefault();
    const query = searchQuery.trim();
    navigate(query ? libraryBrowsePath({ q: query }) : libraryBrowsePath());
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
      eyebrow="Your cinema"
    >
      <main className="explore-main">
        <LibrarySearchBar
          testId="explore-search"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          onSubmit={handleSearchSubmit}
        />

        <section className="explore-hub-links" data-testid="explore-hub-links">
          <Link
            to={libraryBrowsePath({ mediaType: "movie" })}
            className="explore-hub-card"
            data-testid="explore-hub-browse-movies"
          >
            <h2>Movies</h2>
            <p>Page through every film with sort, filters, and columns</p>
          </Link>
          <Link
            to={libraryBrowsePath({ mediaType: "show" })}
            className="explore-hub-card"
            data-testid="explore-hub-browse-tv"
          >
            <h2>TV</h2>
            <p>Page through every series with sort, filters, and columns</p>
          </Link>
          <Link
            to={ROUTES.relatedTitles}
            className="explore-hub-card"
            data-testid="explore-hub-related-titles"
          >
            <h2>Related titles</h2>
            <p>Start with one title, follow its connections, and see why each match belongs</p>
          </Link>
          <Link to={ROUTES.tags} className="explore-hub-card" data-testid="explore-hub-tags">
            <h2>Tags</h2>
            <p>Browse keyword tags across your full library</p>
          </Link>
        </section>

        <ExploreSection
          id="continue-watching"
          title="Continue Watching"
          subtitle="Pick up where you left off — in-progress titles from Plex"
          isOwner={isOwner}
          empty={
            continueWatching.error ||
            (!continueWatching.loading && !continueWatching.items.length ? continueWatching.note : null)
          }
        >
          <FeedRail
            testId="explore-continue-watching-rail"
            items={continueWatching.items}
            loading={continueWatching.loading}
            cardMeta={(item) => item.resume_label || null}
            chatHref={
              continueWatching.items.length
                ? chatFromRailHref({
                    railTitle: "Continue Watching",
                    items: continueWatching.items,
                  })
                : null
            }
            {...recommendProps}
          />
        </ExploreSection>

        {isYouth ? (
          <ExploreSection
            id="pick-for-me"
            title="Pick for me"
            subtitle="Spin up a handful of age-friendly titles you haven't watched yet"
            isOwner={isOwner}
            empty={
              pickForMe.error ||
              (!pickForMe.loading && !pickForMe.items.length
                ? "No picks right now — try Ask instead."
                : null)
            }
          >
            {pickForMe.meta?.live_station?.id ? (
              <p className="explore-live-suggest" data-testid="explore-pick-for-me-live">
                Live is on — try{" "}
                <Link to={liveWatchHref(pickForMe.meta.live_station.id)}>
                  {pickForMe.meta.live_station.name || "a youth-safe station"}
                </Link>
                {pickForMe.meta.live_station.now_title
                  ? ` (now: ${pickForMe.meta.live_station.now_title})`
                  : ""}
                .
              </p>
            ) : null}
            <FeedRail
              testId="explore-pick-for-me-rail"
              items={pickForMe.items}
              loading={pickForMe.loading}
              chatHref={
                pickForMe.items.length
                  ? chatFromRailHref({
                      railTitle: "Pick for me",
                      items: pickForMe.items,
                    })
                  : null
              }
            />
          </ExploreSection>
        ) : null}

        {!isYouth ? <TonightDoubleFeatureHabit /> : null}

        <WhatsOnTonightHabit compact isYouth={isYouth} />

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
            chatHref={
              recentlyAdded.items.length
                ? chatFromRailHref({ railTitle: "Recently Added", items: recentlyAdded.items })
                : null
            }
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
              href: libraryBrowsePath({ mediaType: "movie" }),
            },
            {
              mediaType: "show",
              label: "TV",
              href: libraryBrowsePath({ mediaType: "show" }),
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
          id="on-this-day"
          title="On This Day"
          subtitle={otdSubtitle}
          isOwner={isOwner}
          empty={onThisDay.error || (!onThisDay.loading && !onThisDay.items.length ? onThisDay.note : null)}
          note={onThisDay.items.length && onThisDay.note && !onThisDay.error ? onThisDay.note : null}
        >
          {isOwner && onThisDay.items.length ? (
            <div className="explore-anniversary-live" data-testid="explore-anniversary-live">
              <button
                type="button"
                className="ghost"
                disabled={anniversaryBusy}
                data-testid="explore-anniversary-live-suggest"
                onClick={async () => {
                  setAnniversaryBusy(true);
                  setAnniversaryNote("");
                  try {
                    const preview = await anniversaryLiveStarter({ confirm: false });
                    if (preview?.needs_confirm) {
                      const ok = window.confirm(
                        preview.message || "Put a Live starter on the air for today’s On This Day?",
                      );
                      if (!ok) return;
                      const confirmed = await anniversaryLiveStarter({
                        confirm: true,
                        motifHint: preview.motif_hint || "",
                      });
                      setAnniversaryNote(
                        confirmed.message ||
                          "Starter ready — confirm publish in Live Channels → Stations.",
                      );
                    } else {
                      setAnniversaryNote(preview.message || "No starter available.");
                    }
                  } catch (err) {
                    setAnniversaryNote(err.message || "Could not suggest a Live starter.");
                  } finally {
                    setAnniversaryBusy(false);
                  }
                }}
              >
                {anniversaryBusy ? "Suggesting…" : "Suggest a Live starter for today"}
              </button>
              {anniversaryNote ? (
                <p className="status status-secondary" data-testid="explore-anniversary-live-note">
                  {anniversaryNote}
                </p>
              ) : null}
            </div>
          ) : null}
          <FeedRail
            testId="explore-on-this-day-rail"
            items={onThisDay.items}
            loading={onThisDay.loading}
            {...recommendProps}
          />
        </ExploreSection>

        {directorSpotlight.items.length || directorSpotlight.loading ? (
          <ExploreSection
            id="director-spotlight"
            title={`Films by ${directorSpotlight.meta?.director || "a director"}`}
            subtitle="A daily rotating filmography from your shelves"
            titleHref={directorSpotlight.meta?.director ? exploreFacetPath("directors", directorSpotlight.meta.director) : null}
            isOwner={isOwner}
            empty={directorSpotlight.error || (!directorSpotlight.loading && !directorSpotlight.items.length ? directorSpotlight.note : null)}
          >
            <FeedRail
              testId="explore-director-spotlight-rail"
              items={directorSpotlight.items}
              loading={directorSpotlight.loading}
              {...recommendProps}
            />
          </ExploreSection>
        ) : null}

        {genreSpotlight.items.length || genreSpotlight.loading ? (
          <ExploreSection
            id="genre-spotlight"
            title={`${genreSpotlight.meta?.genre || "Genre"} in your library`}
            subtitle="A daily rotating corner of your collection"
            titleHref={genreSpotlight.meta?.genre ? exploreFacetPath("genre", genreSpotlight.meta.genre) : null}
            isOwner={isOwner}
            empty={genreSpotlight.error || (!genreSpotlight.loading && !genreSpotlight.items.length ? genreSpotlight.note : null)}
          >
            <FeedRail
              testId="explore-genre-spotlight-rail"
              items={genreSpotlight.items}
              loading={genreSpotlight.loading}
              {...recommendProps}
            />
          </ExploreSection>
        ) : null}

        {seasonalSpotlight.items.length || seasonalSpotlight.loading ? (
          <ExploreSection
            id="seasonal-spotlight"
            title={seasonalSpotlight.meta?.label || "Seasonal picks"}
            subtitle={seasonalSpotlight.meta?.mode === "holiday" ? "A nearby calendar occasion, found in your library" : "A light seasonal turn through your library"}
            isOwner={isOwner}
            empty={seasonalSpotlight.error || (!seasonalSpotlight.loading && !seasonalSpotlight.items.length ? seasonalSpotlight.note : null)}
          >
            <FeedRail
              testId="explore-seasonal-spotlight-rail"
              items={seasonalSpotlight.items}
              loading={seasonalSpotlight.loading}
              {...recommendProps}
            />
          </ExploreSection>
        ) : null}

        <div className="explore-footer" data-testid="explore-footer">
        <ExploreSection
          id="library-pulse"
          title="Library Pulse"
          subtitle="A quick read on collection health"
          helpAnchorId="what-knowledge-coverage-means"
          helpTitle="What Library Pulse & knowledge coverage mean"
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
          <KnowledgeCoverageCard variant="strip" className="explore-footer-knowledge" />
        </div>

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

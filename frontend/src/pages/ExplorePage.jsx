import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  getExploreFeedOnThisDay,
  getExploreFeedRecentReleases,
  getExploreFeedRecentlyAdded,
  getLibraryFacets,
  getLibraryHealth,
  getLibraryMotifs,
  getLibraryNeighbors,
  getLibraryOverview,
  queryLibrary,
} from "../api/client";
import { tagPath } from "../lib/browseLinks.js";
import {
  buildMotifQueryParams,
  buildPulseStats,
  normalizeFeed,
  normalizeMotifFacets,
  toggleMotifSelection,
} from "../lib/exploreFeeds.js";
import { titleDetailPath } from "../lib/titleLinks.js";

function ExplorePosterCard({ item, meta, onSeed, seedLabel = "Surprise from this" }) {
  const path = titleDetailPath({
    ...item,
    in_library: true,
  });
  const media = item.poster_url ? (
    <img src={item.poster_url} alt="" loading="lazy" />
  ) : (
    <div className="poster-fallback">{item.title?.slice(0, 1) || "?"}</div>
  );
  const body = (
    <>
      <div className="explore-poster">{media}</div>
      <h3>{item.title || "Untitled"}</h3>
      {item.year ? <p className="explore-card-meta">{item.year}</p> : null}
      {meta ? <p className="explore-card-meta explore-card-context">{meta}</p> : null}
    </>
  );
  return (
    <article className="explore-cinema-card" data-testid="explore-title-card">
      {path ? (
        <Link to={path} className="explore-cinema-card-link">
          {body}
        </Link>
      ) : (
        <div className="explore-cinema-card-link">{body}</div>
      )}
      {onSeed && item.id != null ? (
        <button
          type="button"
          className="ghost explore-seed-btn"
          data-testid="explore-seed-btn"
          onClick={() => onSeed(item)}
        >
          {seedLabel}
        </button>
      ) : null}
    </article>
  );
}

function ExploreSection({ id, title, subtitle, children, empty, note }) {
  const message = empty || note || null;
  return (
    <section className="explore-section" data-testid={`explore-section-${id}`}>
      <header className="explore-section-header">
        <div>
          <h2>{title}</h2>
          {subtitle ? <p className="explore-section-subtitle">{subtitle}</p> : null}
        </div>
      </header>
      {message ? <p className="explore-empty status status-secondary">{message}</p> : null}
      {children}
    </section>
  );
}

function FeedRail({ testId, items, loading, cardMeta, onSeed }) {
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
        />
      ))}
    </div>
  );
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
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const recentlyAdded = useFeed(() => getExploreFeedRecentlyAdded({ limit: 12, days: 30 }), []);
  const recentReleases = useFeed(() => getExploreFeedRecentReleases({ limit: 12, days: 90 }), []);
  const onThisDay = useFeed(() => getExploreFeedOnThisDay({ limit: 12 }), []);

  const [pulse, setPulse] = useState({ loading: true, stats: [], error: "" });
  const [motifs, setMotifs] = useState([]);
  const [motifsNote, setMotifsNote] = useState("");
  const [motifsLoading, setMotifsLoading] = useState(true);
  const [selectedMotifs, setSelectedMotifs] = useState([]);
  const [motifWall, setMotifWall] = useState({ loading: false, items: [], note: null, error: "" });
  const [seed, setSeed] = useState(null);
  const [seedQuery, setSeedQuery] = useState("");
  const [seedHits, setSeedHits] = useState([]);
  const [neighbors, setNeighbors] = useState({ loading: false, items: [], note: null, error: "" });
  const [tagFacets, setTagFacets] = useState([]);
  const [tagsLoading, setTagsLoading] = useState(true);
  const [tagsNote, setTagsNote] = useState("");
  const [tagSearch, setTagSearch] = useState("");
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
    let cancelled = false;
    setMotifsLoading(true);
    getLibraryMotifs({ limit: 40 })
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
    let cancelled = false;
    setTagsLoading(true);
    getLibraryFacets("keyword", 60)
      .then((data) => {
        if (cancelled) return;
        const facets = Array.isArray(data?.facets) ? data.facets : [];
        setTagFacets(
          facets
            .map((entry) => ({
              value: String(entry.value || entry.name || "").trim(),
              count: Number(entry.count || 0) || 0,
            }))
            .filter((entry) => entry.value),
        );
        setTagsNote(facets.length ? "" : "No keyword tags indexed yet.");
        setTagsLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setTagFacets([]);
        setTagsNote(err.message || "Could not load tags.");
        setTagsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const genre = String(searchParams.get("genre") || "").trim();
    const cast = String(searchParams.get("cast") || "").trim();
    const directors = String(searchParams.get("directors") || "").trim();
    if (!genre && !cast && !directors) {
      setFacetWall({ loading: false, items: [], note: null, error: "", label: "" });
      return undefined;
    }
    const filters = { limit: 24 };
    let label = "";
    if (genre) {
      filters.genres = [genre];
      label = `Genre: ${genre}`;
    } else if (cast) {
      filters.cast = [cast];
      label = `Cast: ${cast}`;
    } else if (directors) {
      filters.directors = [directors];
      label = `Director: ${directors}`;
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
  }, [searchParams]);

  useEffect(() => {
    if (!selectedMotifs.length) {
      setMotifWall({ loading: false, items: [], note: null, error: "" });
      return undefined;
    }
    let cancelled = false;
    setMotifWall((prev) => ({ ...prev, loading: true, error: "" }));
    const params = buildMotifQueryParams(selectedMotifs, { limit: 24 });
    queryLibrary(Object.fromEntries(params.entries()))
      .then((data) => {
        if (cancelled) return;
        const items = Array.isArray(data?.items) ? data.items : [];
        setMotifWall({
          loading: false,
          items,
          note: items.length ? null : "No titles match the selected motifs.",
          error: "",
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setMotifWall({
          loading: false,
          items: [],
          note: null,
          error: err.message || "Could not filter by motifs.",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [selectedMotifs]);

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
      queryLibrary({ query: q, limit: 6 })
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
  }, [seedQuery]);

  const otdSubtitle = useMemo(() => {
    const mode = onThisDay.meta?.mode;
    if (mode === "calendar") return "Release anniversaries sharing today’s date";
    if (mode === "milestone_fallback") return "Milestone-year picks from your shelves";
    return "Anniversary picks from your shelves";
  }, [onThisDay.meta?.mode]);

  function handleToggleMotif(value) {
    setSelectedMotifs((prev) => toggleMotifSelection(prev, value));
  }

  function handleSeed(item) {
    setSeed(item);
    setSeedQuery(item.title || "");
    setSeedHits([]);
  }

  const filteredTagFacets = useMemo(() => {
    const q = tagSearch.trim().toLowerCase();
    if (!q) return tagFacets;
    return tagFacets.filter((facet) => facet.value.toLowerCase().includes(q));
  }, [tagFacets, tagSearch]);

  function goToTag(name) {
    const path = tagPath(name);
    if (path) navigate(path);
  }

  function handleTagSearchSubmit(event) {
    event.preventDefault();
    const value = tagSearch.trim();
    if (value) goToTag(value);
  }

  return (
    <div className="app-root explore-page" data-testid="explore-page">
      <header className="app-topbar">
        <div className="app-topbar-brand">
          <div className="app-topbar-titles">
            <h1>Explore</h1>
            <p className="app-topbar-eyebrow">Browse your cinema</p>
          </div>
        </div>
        <div className="app-topbar-actions">
          <Link to="/" className="app-topbar-link" data-testid="explore-back-chat">
            Back to chat
          </Link>
        </div>
      </header>

      <main className="explore-main">
        <ExploreSection
          id="recently-added"
          title="Recently Added"
          subtitle="Fresh arrivals from the last 30 days"
          empty={recentlyAdded.error || (!recentlyAdded.loading && !recentlyAdded.items.length ? recentlyAdded.note : null)}
        >
          <FeedRail
            testId="explore-recently-added-rail"
            items={recentlyAdded.items}
            loading={recentlyAdded.loading}
          />
        </ExploreSection>

        <ExploreSection
          id="recent-releases"
          title="Recent Releases"
          subtitle="Library titles released in the last 90 days"
          empty={
            recentReleases.error ||
            (!recentReleases.loading && !recentReleases.items.length ? recentReleases.note : null)
          }
        >
          <FeedRail
            testId="explore-recent-releases-rail"
            items={recentReleases.items}
            loading={recentReleases.loading}
          />
        </ExploreSection>

        <ExploreSection
          id="library-pulse"
          title="Library Pulse"
          subtitle="A quick read on collection health"
          empty={pulse.error || (!pulse.loading && !pulse.stats.length ? "No overview stats yet." : null)}
        >
          {pulse.loading ? (
            <p className="status status-secondary">Loading pulse…</p>
          ) : pulse.stats.length ? (
            <div className="explore-pulse-grid" data-testid="explore-pulse-grid">
              {pulse.stats.map((stat) => (
                <div key={stat.id} className="explore-pulse-stat" data-testid={`explore-pulse-${stat.id}`}>
                  <span className="explore-pulse-value">{stat.value}</span>
                  <span className="explore-pulse-label">{stat.label}</span>
                  {stat.detail ? <span className="explore-pulse-detail">{stat.detail}</span> : null}
                </div>
              ))}
            </div>
          ) : null}
        </ExploreSection>

        <ExploreSection
          id="on-this-day"
          title="On This Day"
          subtitle={otdSubtitle}
          empty={onThisDay.error || (!onThisDay.loading && !onThisDay.items.length ? onThisDay.note : null)}
          note={
            onThisDay.items.length && onThisDay.note && !onThisDay.error ? onThisDay.note : null
          }
        >
          <FeedRail
            testId="explore-on-this-day-rail"
            items={onThisDay.items}
            loading={onThisDay.loading}
          />
        </ExploreSection>

        {facetWall.label ? (
          <ExploreSection
            id="facet-filter"
            title={facetWall.label}
            subtitle="Deep-link filter from title detail"
            empty={facetWall.error || facetWall.note}
          >
            {facetWall.loading ? (
              <p className="status status-secondary">Loading titles…</p>
            ) : facetWall.items.length ? (
              <div className="explore-poster-wall" data-testid="explore-facet-wall">
                {facetWall.items.map((item) => (
                  <ExplorePosterCard
                    key={item.id || item.rating_key || item.title}
                    item={item}
                  />
                ))}
              </div>
            ) : null}
          </ExploreSection>
        ) : null}

        <ExploreSection
          id="tags"
          title="Tags"
          subtitle="Browse keyword tags from your library"
          empty={tagsLoading ? null : tagsNote && !tagFacets.length ? tagsNote : null}
        >
          <form
            className="explore-tag-search"
            data-testid="explore-tag-search"
            onSubmit={handleTagSearchSubmit}
          >
            <label className="explore-seed-label" htmlFor="explore-tag-input">
              Find a tag
            </label>
            <div className="explore-tag-search-row">
              <input
                id="explore-tag-input"
                className="explore-seed-input"
                data-testid="explore-tag-input"
                type="search"
                placeholder="time travel, heist, found footage…"
                value={tagSearch}
                onChange={(e) => setTagSearch(e.target.value)}
                autoComplete="off"
              />
              <button type="submit" className="ghost" data-testid="explore-tag-submit">
                Open tag
              </button>
            </div>
          </form>
          {tagsLoading ? (
            <p className="status status-secondary">Loading tags…</p>
          ) : filteredTagFacets.length ? (
            <div className="explore-motif-chips" data-testid="explore-tag-chips">
              {filteredTagFacets.map((facet) => (
                <button
                  key={facet.value}
                  type="button"
                  className="explore-motif-chip"
                  data-testid="explore-tag-chip"
                  onClick={() => goToTag(facet.value)}
                >
                  {facet.value}
                  {facet.count ? <span className="explore-motif-count">{facet.count}</span> : null}
                </button>
              ))}
            </div>
          ) : tagSearch.trim() ? (
            <p className="explore-empty status status-secondary">
              No matching facet chips — press Open tag to browse “{tagSearch.trim()}” anyway.
            </p>
          ) : null}
        </ExploreSection>

        <ExploreSection
          id="plot-lab"
          title="Plot Lab"
          subtitle="Motifs, poster walls, and surprising narrative neighbors"
          empty={motifsLoading ? null : motifsNote && !motifs.length ? motifsNote : null}
        >
          {motifsLoading ? (
            <p className="status status-secondary">Loading motifs…</p>
          ) : motifs.length ? (
            <div className="explore-motif-chips" data-testid="explore-motif-chips">
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
          ) : null}

          {selectedMotifs.length ? (
            <div className="explore-plot-lab-wall" data-testid="explore-motif-wall">
              <h3 className="explore-plot-lab-heading">Motif wall</h3>
              {motifWall.error || motifWall.note ? (
                <p className="explore-empty status status-secondary">
                  {motifWall.error || motifWall.note}
                </p>
              ) : null}
              {motifWall.loading ? (
                <p className="status status-secondary">Filtering titles…</p>
              ) : motifWall.items.length ? (
                <div className="explore-poster-wall">
                  {motifWall.items.map((item) => (
                    <ExplorePosterCard
                      key={item.id || item.rating_key || item.title}
                      item={item}
                      onSeed={handleSeed}
                    />
                  ))}
                </div>
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
              <p className="explore-empty status status-secondary">
                {neighbors.error || neighbors.note}
              </p>
            ) : null}
            <FeedRail
              testId="explore-neighbors-rail"
              items={neighbors.items}
              loading={neighbors.loading}
            />
          </div>
        </ExploreSection>
      </main>
    </div>
  );
}

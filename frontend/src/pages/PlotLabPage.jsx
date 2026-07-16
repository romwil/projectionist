import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  getLibraryMotifs,
  getLibraryNeighbors,
  queryLibrary,
} from "../api/client";
import AppNav, { AppNavToggle } from "../components/AppNav";
import BackLink from "../components/BackLink";
import LibraryMediaCard from "../components/LibraryMediaCard";
import RecommendModal from "../components/RecommendModal";
import { useAuthGate } from "../components/UserMenu";
import { ROUTES } from "../lib/browseLinks.js";
import {
  buildMotifQueryParams,
  normalizeFeed,
  normalizeMotifFacets,
  toggleMotifSelection,
} from "../lib/exploreFeeds.js";

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

export default function PlotLabPage() {
  const { isOwner, multiUserEnabled } = useAuthGate();
  const [navOpen, setNavOpen] = useState(false);
  const [motifs, setMotifs] = useState([]);
  const [motifsNote, setMotifsNote] = useState("");
  const [motifsLoading, setMotifsLoading] = useState(true);
  const [selectedMotifs, setSelectedMotifs] = useState([]);
  const [motifWall, setMotifWall] = useState({ loading: false, items: [], note: null, error: "" });
  const [seed, setSeed] = useState(null);
  const [seedQuery, setSeedQuery] = useState("");
  const [seedHits, setSeedHits] = useState([]);
  const [neighbors, setNeighbors] = useState({ loading: false, items: [], note: null, error: "" });
  const [recommendItem, setRecommendItem] = useState(null);

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

  function handleToggleMotif(value) {
    setSelectedMotifs((prev) => toggleMotifSelection(prev, value));
  }

  function handleSeed(item) {
    setSeed(item);
    setSeedQuery(item.title || "");
    setSeedHits([]);
  }

  return (
    <div className="app-root explore-page plot-lab-page" data-testid="plot-lab-page">
      <AppNav open={navOpen} onClose={() => setNavOpen(false)} isOwner={isOwner} />
      <header className="app-topbar">
        <div className="app-topbar-brand">
          <AppNavToggle open={navOpen} onClick={() => setNavOpen(true)} />
          <div className="app-topbar-titles">
            <h1>Plot Lab</h1>
            <p className="app-topbar-eyebrow">Motifs, poster walls, and surprising narrative neighbors</p>
          </div>
        </div>
        <div className="app-topbar-actions">
          <BackLink fallbackTo={ROUTES.explore} testId="plot-lab-back" />
        </div>
      </header>

      <main className="explore-main">
        {motifsLoading ? (
          <p className="status status-secondary">Loading motifs…</p>
        ) : motifsNote && !motifs.length ? (
          <p className="explore-empty status status-secondary">{motifsNote}</p>
        ) : null}

        {motifs.length ? (
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
                  <LibraryMediaCard
                    key={item.id || item.rating_key || item.title}
                    item={item}
                    onSeed={handleSeed}
                    showRecommend={multiUserEnabled}
                    onRecommend={multiUserEnabled ? setRecommendItem : undefined}
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
    </div>
  );
}

import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getLibraryFacets } from "../api/client";
import AppNav, { AppNavToggle } from "../components/AppNav";
import BackLink from "../components/BackLink";
import { useAuthGate } from "../components/UserMenu";
import { ROUTES, tagPath, withReturnTo } from "../lib/browseLinks.js";
import {
  normalizeFacetHits,
  shouldQueryFacetIndex,
  tagSearchEmptyMessage,
} from "../lib/tagSearch.js";

export default function TagsPage() {
  const navigate = useNavigate();
  const { isOwner } = useAuthGate();
  const [navOpen, setNavOpen] = useState(false);
  const [tagSearch, setTagSearch] = useState("");
  const [popular, setPopular] = useState([]);
  const [hits, setHits] = useState([]);
  const [loadingPopular, setLoadingPopular] = useState(true);
  const [searching, setSearching] = useState(false);
  const [note, setNote] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoadingPopular(true);
    getLibraryFacets("keyword", 60)
      .then((data) => {
        if (cancelled) return;
        const facets = normalizeFacetHits(data);
        setPopular(facets);
        setNote(facets.length ? "" : "No keyword tags indexed yet.");
        setLoadingPopular(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setPopular([]);
        setNote(err.message || "Could not load tags.");
        setLoadingPopular(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const q = tagSearch.trim();
    if (!shouldQueryFacetIndex(q)) {
      setHits([]);
      setSearching(false);
      return undefined;
    }
    let cancelled = false;
    setSearching(true);
    const timer = setTimeout(() => {
      getLibraryFacets("keyword", 40, q)
        .then((data) => {
          if (cancelled) return;
          setHits(normalizeFacetHits(data));
          setSearching(false);
        })
        .catch(() => {
          if (cancelled) return;
          setHits([]);
          setSearching(false);
        });
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [tagSearch]);

  function goToTag(name) {
    const path = tagPath(name);
    if (path) {
      navigate(path, { state: withReturnTo(ROUTES.tags) });
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    const value = tagSearch.trim();
    if (value) goToTag(value);
  }

  const q = tagSearch.trim();
  const showHits = shouldQueryFacetIndex(q);
  const chips = showHits ? hits : popular;

  return (
    <div className="app-root explore-page tags-page" data-testid="tags-page">
      <AppNav open={navOpen} onClose={() => setNavOpen(false)} isOwner={isOwner} />
      <header className="app-topbar">
        <div className="app-topbar-brand">
          <AppNavToggle open={navOpen} onClick={() => setNavOpen(true)} />
          <div className="app-topbar-titles">
            <h1>Tags</h1>
            <p className="app-topbar-eyebrow">Browse keyword tags from your library</p>
          </div>
        </div>
        <div className="app-topbar-actions">
          <BackLink fallbackTo={ROUTES.explore} testId="tags-back" />
        </div>
      </header>

      <main className="explore-main">
        <form className="explore-tag-search" data-testid="explore-tag-search" onSubmit={handleSubmit}>
          <label className="explore-seed-label" htmlFor="tags-page-input">
            Find a tag
          </label>
          <div className="explore-tag-search-row">
            <input
              id="tags-page-input"
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

        {loadingPopular && !showHits ? (
          <p className="status status-secondary">Loading tags…</p>
        ) : null}
        {showHits && searching ? (
          <p className="status status-secondary" data-testid="tag-search-status">
            Searching tags…
          </p>
        ) : null}
        {showHits && !searching && !chips.length ? (
          <p className="explore-empty status status-secondary" data-testid="tag-search-empty">
            {tagSearchEmptyMessage(q)}
          </p>
        ) : null}
        {!showHits && note && !popular.length ? (
          <p className="explore-empty status status-secondary">{note}</p>
        ) : null}

        {chips.length ? (
          <div className="explore-motif-chips" data-testid="explore-tag-chips">
            {chips.map((facet) => (
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
        ) : null}

        <p className="explore-hub-link-row">
          <Link to={ROUTES.explore} className="app-topbar-link">
            Explore hub
          </Link>
          <Link to={ROUTES.plotLab} className="app-topbar-link">
            Plot Lab
          </Link>
        </p>
      </main>
    </div>
  );
}

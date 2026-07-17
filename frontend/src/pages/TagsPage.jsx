import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getLibraryFacets } from "../api/client";
import BackLink from "../components/BackLink";
import AppShell from "../layouts/AppShell";
import { ROUTES, tagPath, withReturnTo } from "../lib/browseLinks.js";
import {
  buildAndTagPath,
  moveTypeaheadIndex,
  normalizeFacetHits,
  shouldQueryFacetIndex,
  tagSearchEmptyMessage,
  toggleTagSelection,
} from "../lib/tagSearch.js";

export default function TagsPage() {
  const navigate = useNavigate();
  const [tagSearch, setTagSearch] = useState("");
  const [popular, setPopular] = useState([]);
  const [hits, setHits] = useState([]);
  const [loadingPopular, setLoadingPopular] = useState(true);
  const [searching, setSearching] = useState(false);
  const [note, setNote] = useState("");
  const [highlight, setHighlight] = useState(-1);
  const [selected, setSelected] = useState([]);

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
      setHighlight(-1);
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
          setHighlight(-1);
        })
        .catch(() => {
          if (cancelled) return;
          setHits([]);
          setSearching(false);
          setHighlight(-1);
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

  function goToSelectedAnd() {
    const path = buildAndTagPath(tagPath, selected);
    if (path) {
      navigate(path, { state: withReturnTo(ROUTES.tags) });
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    if (selected.length > 1) {
      goToSelectedAnd();
      return;
    }
    if (highlight >= 0 && chips[highlight]) {
      goToTag(chips[highlight].value);
      return;
    }
    const value = tagSearch.trim();
    if (value) goToTag(value);
  }

  function handleInputKeyDown(event) {
    if (!chips.length) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp" || event.key === "Home" || event.key === "End") {
      event.preventDefault();
      setHighlight((current) => moveTypeaheadIndex(current, event.key, chips.length));
      return;
    }
    if (event.key === "Enter" && highlight >= 0 && chips[highlight]) {
      event.preventDefault();
      goToTag(chips[highlight].value);
    }
  }

  const q = tagSearch.trim();
  const showHits = shouldQueryFacetIndex(q);
  const chips = showHits ? hits : popular;

  return (
    <AppShell
      className="app-root explore-page tags-page"
      testId="tags-page"
      title="Tags"
      eyebrow="Browse keyword tags from your library"
      actions={<BackLink fallbackTo={ROUTES.explore} testId="tags-back" />}
    >
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
              onKeyDown={handleInputKeyDown}
              autoComplete="off"
              aria-autocomplete="list"
              aria-controls="explore-tag-chips"
              aria-activedescendant={
                highlight >= 0 && chips[highlight] ? `tag-option-${chips[highlight].value}` : undefined
              }
            />
            <button type="submit" className="ghost" data-testid="explore-tag-submit">
              Open tag
            </button>
          </div>
          <p className="status status-secondary explore-tag-hint">
            Arrow keys highlight results. Shift-click chips to AND-filter.
          </p>
        </form>

        {selected.length ? (
          <div className="tag-and-bar" data-testid="tag-and-bar">
            <p className="explore-section-subtitle">
              AND filter: {selected.join(" + ")}
            </p>
            <div className="tag-and-actions">
              <button
                type="button"
                className="ghost"
                data-testid="tag-and-apply"
                onClick={goToSelectedAnd}
              >
                Show matching titles
              </button>
              <button
                type="button"
                className="ghost"
                data-testid="tag-and-clear"
                onClick={() => setSelected([])}
              >
                Clear
              </button>
            </div>
          </div>
        ) : null}

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
          <div className="explore-motif-chips" data-testid="explore-tag-chips" id="explore-tag-chips">
            {chips.map((facet, index) => {
              const isSelected = selected.includes(facet.value);
              const isActive = index === highlight;
              return (
                <button
                  key={facet.value}
                  id={`tag-option-${facet.value}`}
                  type="button"
                  className={`explore-motif-chip${isActive ? " is-typeahead-active" : ""}${
                    isSelected ? " is-and-selected" : ""
                  }`}
                  data-testid="explore-tag-chip"
                  aria-selected={isActive}
                  onClick={(event) => {
                    if (event.shiftKey || event.metaKey || event.ctrlKey) {
                      setSelected((prev) => toggleTagSelection(prev, facet.value));
                      return;
                    }
                    goToTag(facet.value);
                  }}
                >
                  {facet.value}
                  {facet.count ? <span className="explore-motif-count">{facet.count}</span> : null}
                </button>
              );
            })}
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
    </AppShell>
  );
}

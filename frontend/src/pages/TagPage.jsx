import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { queryLibrary } from "../api/client";
import BackLink from "../components/BackLink";
import LibraryMediaCard from "../components/LibraryMediaCard";
import RecommendModal from "../components/RecommendModal";
import { useAuthGate } from "../components/UserMenu";
import AppShell from "../layouts/AppShell";
import { ROUTES } from "../lib/browseLinks.js";
import {
  TAG_SORT_OPTIONS,
  normalizeTagSort,
  parseAndTags,
} from "../lib/tagSearch.js";

export default function TagPage() {
  const { tagName } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const decoded = decodeURIComponent(String(tagName || ""));
  const andTags = useMemo(() => parseAndTags(searchParams), [searchParams]);
  const keywords = useMemo(
    () => [decoded, ...andTags].map((t) => t.trim()).filter(Boolean),
    [decoded, andTags],
  );
  const sort = normalizeTagSort(searchParams.get("sort"));
  const { multiUserEnabled } = useAuthGate();
  const [recommendItem, setRecommendItem] = useState(null);
  const [state, setState] = useState({ loading: true, items: [], error: "" });

  useEffect(() => {
    let cancelled = false;
    setState({ loading: true, items: [], error: "" });
    queryLibrary({ keywords, limit: 48, sort })
      .then((data) => {
        if (cancelled) return;
        setState({
          loading: false,
          items: Array.isArray(data?.items) ? data.items : [],
          error: "",
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setState({
          loading: false,
          items: [],
          error: err.message || "Could not load titles for this tag.",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [keywords, sort]);

  function handleSortChange(nextSort) {
    const params = new URLSearchParams(searchParams);
    const normalized = normalizeTagSort(nextSort);
    if (normalized === "title") params.delete("sort");
    else params.set("sort", normalized);
    setSearchParams(params, { replace: true });
  }

  return (
    <AppShell
      className="app-root tag-page"
      testId="tag-page"
      variant="browse"
      leading={<BackLink fallbackTo={ROUTES.tags} testId="tag-back" />}
      actions={
        <Link to={ROUTES.tags} className="app-topbar-link" data-testid="tag-back-explore">
          Tag search
        </Link>
      }
    >
      <section className="tag-hero" data-testid="tag-hero">
        <p className="person-eyebrow">Tag{keywords.length > 1 ? "s (AND)" : ""}</p>
        <h1 data-testid="tag-name">{keywords.join(" + ") || "Untitled tag"}</h1>
        <p className="explore-section-subtitle">
          Library titles tagged with {keywords.length > 1 ? "all of these keywords" : "this keyword"}
        </p>
        <label className="tag-sort-control">
          <span>Sort</span>
          <select
            value={sort}
            data-testid="tag-sort"
            onChange={(event) => handleSortChange(event.target.value)}
          >
            {TAG_SORT_OPTIONS.map((opt) => (
              <option key={opt.id} value={opt.sort}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
      </section>

      <section className="tag-results" data-testid="tag-results">
        {state.loading ? <p className="status status-secondary">Loading…</p> : null}
        {state.error ? <p className="error">{state.error}</p> : null}
        {!state.loading && !state.error && !state.items.length ? (
          <p className="explore-empty status status-secondary" data-testid="tag-empty">
            No library titles match {keywords.length > 1 ? "these tags" : "this tag"} yet.
          </p>
        ) : null}
        {state.items.length ? (
          <div className="explore-poster-wall">
            {state.items.map((item) => (
              <LibraryMediaCard
                key={item.id || item.rating_key || `${item.media_type}-${item.tmdb_id || item.title}`}
                item={item}
                testId="tag-title-card"
                showRecommend={multiUserEnabled}
                onRecommend={multiUserEnabled ? setRecommendItem : undefined}
              />
            ))}
          </div>
        ) : null}
      </section>

      <RecommendModal
        item={recommendItem}
        open={Boolean(recommendItem)}
        onClose={() => setRecommendItem(null)}
      />
    </AppShell>
  );
}

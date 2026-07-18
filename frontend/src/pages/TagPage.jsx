import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { queryLibrary } from "../api/client";
import BackLink from "../components/BackLink";
import LibraryMediaCard from "../components/LibraryMediaCard";
import MediaBrowseControls from "../components/MediaBrowseControls";
import MediaBrowseResults from "../components/MediaBrowseResults";
import RecommendModal from "../components/RecommendModal";
import { useAuthGate } from "../components/UserMenu";
import AppShell from "../layouts/AppShell";
import { ROUTES } from "../lib/browseLinks.js";
import {
  TAG_SORT_OPTIONS,
  normalizeTagSort,
  parseAndTags,
} from "../lib/tagSearch.js";
import { buildMediaBrowseParams, parseMediaBrowse, queryFiltersFromBrowse } from "../lib/mediaBrowse.js";

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
  const browse = useMemo(() => parseMediaBrowse(searchParams, { sort }), [searchParams, sort]);
  const [columns, setColumns] = useState(null);
  const { multiUserEnabled } = useAuthGate();
  const [recommendItem, setRecommendItem] = useState(null);
  const [state, setState] = useState({ loading: true, items: [], error: "" });

  useEffect(() => {
    let cancelled = false;
    setState({ loading: true, items: [], error: "" });
    queryLibrary({ ...queryFiltersFromBrowse(browse), keywords, limit: browse.limit, sort: browse.sort })
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
  }, [keywords, browse]);

  function handleSortChange(nextSort) {
    const params = new URLSearchParams(searchParams);
    const normalized = normalizeTagSort(nextSort);
    if (normalized === "title") params.delete("sort");
    else params.set("sort", normalized);
    setSearchParams(params, { replace: true });
  }

  function handleBrowseChange(patch) {
    const params = buildMediaBrowseParams(browse, patch);
    params.set("keywords", keywords.join(","));
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
        <MediaBrowseControls state={browse} onChange={handleBrowseChange} columns={columns} onColumnsChange={setColumns} columnScope="tag" />
      </section>

      <section className="tag-results" data-testid="tag-results">
        {state.loading ? <p className="status status-secondary">Loading…</p> : null}
        {state.error ? <p className="error">{state.error}</p> : null}
        {!state.loading && !state.error && !state.items.length ? (
          <p className="explore-empty status status-secondary" data-testid="tag-empty">
            No library titles match {keywords.length > 1 ? "these tags" : "this tag"} yet.
          </p>
        ) : null}
        {state.items.length ? <MediaBrowseResults state={browse} items={state.items} columns={columns || undefined} cardProps={{ testId: "tag-title-card", showRecommend: multiUserEnabled, onRecommend: multiUserEnabled ? setRecommendItem : undefined }} /> : null}
      </section>

      <RecommendModal
        item={recommendItem}
        open={Boolean(recommendItem)}
        onClose={() => setRecommendItem(null)}
      />
    </AppShell>
  );
}

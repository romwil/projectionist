import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { getLibraryAggregate, queryLibrary } from "../api/client";
import BackLink from "../components/BackLink";
import BrowseResultsRegion from "../components/BrowseResultsRegion";
import LibraryMediaCard from "../components/LibraryMediaCard";
import MediaBrowseControls from "../components/MediaBrowseControls";
import MediaBrowsePagination from "../components/MediaBrowsePagination";
import MediaBrowseResults from "../components/MediaBrowseResults";
import RecommendModal from "../components/RecommendModal";
import { useAuthGate } from "../components/UserMenu";
import AppShell from "../layouts/AppShell";
import { ROUTES } from "../lib/browseLinks.js";
import { browseLanguageOptions } from "../lib/languageNames.js";
import { TAG_SORT_OPTIONS, normalizeTagSort, parseAndTags } from "../lib/tagSearch.js";
import {
  MEDIA_BROWSE_PAGE_SIZES,
  buildMediaBrowseParams,
  isAllPageSize,
  parseMediaBrowse,
  queryFiltersFromBrowse,
  resolvePageSizeLimit,
} from "../lib/mediaBrowse.js";

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
  const [columns, setColumns] = useState<any | null>(null);
  const [filterOptions, setFilterOptions] = useState<any>({ years: [] as any[], genres: [] as any[], languages: [] as any[] });
  const { multiUserEnabled } = useAuthGate();
  const [recommendItem, setRecommendItem] = useState<any | null>(null);
  const [state, setState] = useState<any>({
    loading: true,
    items: [] as any[],
    total: 0,
    hasMore: false,
    error: "",
  });

  useEffect(() => {
    let cancelled = false;
    const mediaType =
      browse.media_type === "movie" || browse.media_type === "show" ? browse.media_type : "";
    const aggregateOptions = mediaType ? { mediaType } : {};
    Promise.all([
      getLibraryAggregate("year", aggregateOptions).catch(() => ({ buckets: [] })),
      getLibraryAggregate("genre", aggregateOptions).catch(() => ({ buckets: [] })),
      getLibraryAggregate("language", aggregateOptions).catch(() => ({ buckets: [] })),
    ]).then(([yearAgg, genreAgg, languageAgg]) => {
      if (cancelled) return;
      setFilterOptions({
        years: [
          ...new Set((yearAgg?.buckets || []).map((bucket: any) => bucket.year).filter(Boolean)),
        ].sort((a, b) => (b as any) - (a as any)),
        genres: [
          ...new Set((genreAgg?.buckets || []).map((bucket: any) => bucket.genre).filter(Boolean)),
        ].sort(),
        languages: browseLanguageOptions(
          (languageAgg?.buckets || []).map((bucket: any) => bucket.value),
        ),
      });
    });
    return () => {
      cancelled = true;
    };
  }, [browse.media_type]);

  useEffect(() => {
    let cancelled = false;
    setState((prev: any) => ({ ...prev, loading: true, error: "" }));
    queryLibrary({
      ...queryFiltersFromBrowse(browse),
      keywords,
      limit: resolvePageSizeLimit(browse.limit),
      sort: browse.sort,
    })
      .then((data) => {
        if (cancelled) return;
        const items = Array.isArray(data?.items) ? data.items : [];
        setState({
          loading: false,
          items,
          total: Number(data?.total_matched ?? items.length) || 0,
          hasMore: Boolean(data?.has_more),
          error: "",
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setState({
          loading: false,
          items: [],
          total: 0,
          hasMore: false,
          error: (err as { message?: string }).message || "Could not load titles for this tag.",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [keywords, browse]);

  function handleSortChange(nextSort: any) {
    const params = new URLSearchParams(searchParams);
    const normalized = normalizeTagSort(nextSort);
    if (normalized === "title") params.delete("sort");
    else params.set("sort", normalized);
    setSearchParams(params, { replace: true });
  }

  function handleBrowseChange(patch: any) {
    const params = buildMediaBrowseParams({ ...browse, keywords }, patch);
    params.set("keywords", keywords.join(","));
    setSearchParams(params, { replace: true });
  }

  const isAll = isAllPageSize(browse.limit);
  const pageSize = isAll ? state.items.length || 1 : Number(browse.limit) || 48;
  const page = isAll ? 1 : Math.floor((Number(browse.offset) || 0) / pageSize) + 1;
  const pageCount = isAll ? 1 : Math.max(1, Math.ceil((state.total || 0) / pageSize));
  const paginationSummary = isAll
    ? `${state.total} title${state.total === 1 ? "" : "s"}`
    : `Page ${page} of ${pageCount}${state.total ? ` · ${state.total} titles` : ""}`;

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
          Library titles tagged with{" "}
          {keywords.length > 1 ? "all of these keywords" : "this keyword"}
        </p>
        <div className="explore-section-toolbar" data-testid="tag-browse-toolbar">
          <MediaBrowseControls
            state={{ ...browse, keywords }}
            onChange={handleBrowseChange}
            columns={columns}
            onColumnsChange={setColumns}
            columnScope="tag"
            filterOptions={filterOptions}
            pageSizes={MEDIA_BROWSE_PAGE_SIZES}
          />
          <p className="explore-section-pagination-summary" data-testid="tag-browse-summary">
            {paginationSummary}
          </p>
        </div>
      </section>

      <BrowseResultsRegion
        className="tag-results"
        testId="tag-results"
        loading={state.loading}
        error={state.error}
        hasItems={state.items.length > 0}
        empty={
          <p className="explore-empty status status-secondary" data-testid="tag-empty">
            No library titles match {keywords.length > 1 ? "these tags" : "this tag"} yet.
          </p>
        }
      >
        <MediaBrowseResults
          state={browse}
          items={state.items}
          columns={columns || undefined}
          cardProps={{
            testId: "tag-title-card",
            showRecommend: multiUserEnabled,
            onRecommend: multiUserEnabled ? setRecommendItem : undefined,
          }}
        />
        {!state.loading && !state.error && state.total ? (
          <MediaBrowsePagination
            summary={paginationSummary}
            pageSize={isAll ? "all" : pageSize}
            pageSizes={MEDIA_BROWSE_PAGE_SIZES}
            onPageSizeChange={(limit) => handleBrowseChange({ limit, offset: 0 })}
            hasPrevious={!isAll && Number(browse.offset) > 0}
            hasNext={!isAll && state.hasMore}
            onPrevious={() =>
              handleBrowseChange({ offset: Math.max(0, (Number(browse.offset) || 0) - pageSize) })
            }
            onNext={() => handleBrowseChange({ offset: (Number(browse.offset) || 0) + pageSize })}
            testIdPrefix="tag-browse"
          />
        ) : null}
      </BrowseResultsRegion>

      <RecommendModal
        item={recommendItem}
        open={Boolean(recommendItem)}
        onClose={() => setRecommendItem(null)}
      />
    </AppShell>
  );
}

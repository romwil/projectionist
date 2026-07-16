import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { queryLibrary } from "../api/client";
import AppNav, { AppNavToggle } from "../components/AppNav";
import BackLink from "../components/BackLink";
import LibraryMediaCard from "../components/LibraryMediaCard";
import RecommendModal from "../components/RecommendModal";
import { useAuthGate } from "../components/UserMenu";
import { ROUTES } from "../lib/browseLinks.js";

export default function TagPage() {
  const { tagName } = useParams();
  const decoded = decodeURIComponent(String(tagName || ""));
  const { isOwner, multiUserEnabled } = useAuthGate();
  const [navOpen, setNavOpen] = useState(false);
  const [recommendItem, setRecommendItem] = useState(null);
  const [state, setState] = useState({ loading: true, items: [], error: "" });

  useEffect(() => {
    let cancelled = false;
    setState({ loading: true, items: [], error: "" });
    queryLibrary({ keywords: [decoded], limit: 48, sort: "title" })
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
  }, [decoded]);

  return (
    <div className="app-root tag-page" data-testid="tag-page">
      <AppNav open={navOpen} onClose={() => setNavOpen(false)} isOwner={isOwner} />
      <header className="browse-page-header">
        <div className="browse-page-header-left">
          <AppNavToggle open={navOpen} onClick={() => setNavOpen(true)} />
          <BackLink fallbackTo={ROUTES.tags} testId="tag-back" />
        </div>
        <Link to={ROUTES.tags} className="app-topbar-link" data-testid="tag-back-explore">
          Tag search
        </Link>
      </header>

      <section className="tag-hero" data-testid="tag-hero">
        <p className="person-eyebrow">Tag</p>
        <h1 data-testid="tag-name">{decoded || "Untitled tag"}</h1>
        <p className="explore-section-subtitle">Library titles tagged with this keyword</p>
      </section>

      <section className="tag-results" data-testid="tag-results">
        {state.loading ? <p className="status status-secondary">Loading…</p> : null}
        {state.error ? <p className="error">{state.error}</p> : null}
        {!state.loading && !state.error && !state.items.length ? (
          <p className="explore-empty status status-secondary" data-testid="tag-empty">
            No library titles match this tag yet.
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
    </div>
  );
}

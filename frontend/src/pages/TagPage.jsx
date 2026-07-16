import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { queryLibrary } from "../api/client";
import { titleDetailPath } from "../lib/titleLinks.js";

export default function TagPage() {
  const { tagName } = useParams();
  const decoded = decodeURIComponent(String(tagName || ""));
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
      <header className="browse-page-header">
        <Link to="/" className="title-detail-back">
          ← Back to chat
        </Link>
        <Link to="/explore" className="app-topbar-link" data-testid="tag-back-explore">
          Explore tags
        </Link>
      </header>

      <section className="tag-hero" data-testid="tag-hero">
        <p className="person-eyebrow">Tag</p>
        <h1 data-testid="tag-name">{decoded || "Untitled tag"}</h1>
        <p className="explore-section-subtitle">
          Library titles tagged with this keyword
        </p>
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
            {state.items.map((item) => {
              const path = titleDetailPath({ ...item, in_library: true });
              const key = item.id || item.rating_key || `${item.media_type}-${item.tmdb_id || item.title}`;
              const body = (
                <>
                  <div className="explore-poster">
                    {item.poster_url ? (
                      <img src={item.poster_url} alt="" loading="lazy" />
                    ) : (
                      <div className="poster-fallback">{item.title?.slice(0, 1) || "?"}</div>
                    )}
                  </div>
                  <h3>{item.title || "Untitled"}</h3>
                  {item.year ? <p className="explore-card-meta">{item.year}</p> : null}
                </>
              );
              return (
                <article key={key} className="explore-cinema-card" data-testid="tag-title-card">
                  {path ? (
                    <Link to={path} className="explore-cinema-card-link">
                      {body}
                    </Link>
                  ) : (
                    <div className="explore-cinema-card-link">{body}</div>
                  )}
                </article>
              );
            })}
          </div>
        ) : null}
      </section>
    </div>
  );
}

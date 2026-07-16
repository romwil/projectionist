import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { titleDetailPath } from "../lib/titleLinks.js";

function ExplorePosterCard({ item }) {
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
    </>
  );
  if (path) {
    return (
      <Link to={path} className="explore-cinema-card" data-testid="explore-title-card">
        {body}
      </Link>
    );
  }
  return (
    <article className="explore-cinema-card" data-testid="explore-title-card">
      {body}
    </article>
  );
}

function ExploreSection({ id, title, subtitle, children, empty }) {
  return (
    <section className="explore-section" data-testid={`explore-section-${id}`}>
      <header className="explore-section-header">
        <div>
          <h2>{title}</h2>
          {subtitle ? <p className="explore-section-subtitle">{subtitle}</p> : null}
        </div>
      </header>
      {empty ? <p className="explore-empty status status-secondary">{empty}</p> : null}
      {children}
    </section>
  );
}

function PlaceholderGrid({ label }) {
  return (
    <div className="explore-placeholder-grid" aria-hidden="true">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="explore-placeholder-card">
          <div className="explore-placeholder-poster" />
          <span>{label}</span>
        </div>
      ))}
    </div>
  );
}

export default function ExplorePage() {
  const [recentlyAdded, setRecentlyAdded] = useState(null);
  const [recentError, setRecentError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams({
      sort: "added_at",
      recently_added_days: "30",
      limit: "12",
    });
    api(`/library/query?${params}`)
      .then((data) => {
        if (cancelled) return;
        setRecentlyAdded(Array.isArray(data?.items) ? data.items : []);
      })
      .catch((err) => {
        if (cancelled) return;
        setRecentlyAdded([]);
        setRecentError(err.message || "Could not load recently added titles.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const recentLoading = recentlyAdded === null;
  const recentItems = recentlyAdded || [];

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
          empty={
            recentLoading
              ? null
              : recentError
                ? recentError
                : recentItems.length
                  ? null
                  : "No titles added in the last 30 days — or your library sync hasn’t recorded added dates yet."
          }
        >
          {recentLoading ? (
            <p className="status status-secondary">Loading recently added…</p>
          ) : recentItems.length ? (
            <div className="explore-card-rail" data-testid="explore-recently-added-rail">
              {recentItems.map((item) => (
                <ExplorePosterCard
                  key={item.id || item.rating_key || `${item.media_type}-${item.tmdb_id || item.title}`}
                  item={item}
                />
              ))}
            </div>
          ) : null}
        </ExploreSection>

        <ExploreSection
          id="recent-releases"
          title="Recent Releases"
          subtitle="Coming with release-date enrichment"
          empty="Waiting on release-date data for Wave 3."
        >
          <PlaceholderGrid label="Soon" />
        </ExploreSection>

        <ExploreSection
          id="library-pulse"
          title="Library Pulse"
          subtitle="Taste curves and collection health"
          empty="Pulse charts land once aggregate Explore widgets ship."
        >
          <PlaceholderGrid label="Pulse" />
        </ExploreSection>

        <ExploreSection
          id="on-this-day"
          title="On This Day"
          subtitle="Anniversary picks from your shelves"
          empty="Anniversary browse moves here in a later wave — it’s already on the chat home."
        >
          <PlaceholderGrid label="OTD" />
        </ExploreSection>

        <ExploreSection
          id="plot-lab"
          title="Plot Lab"
          subtitle="Motifs, neighbors, and narrative twins"
          empty="Plot Lab needs Stage 2/3 neighbor + motif APIs."
        >
          <PlaceholderGrid label="Lab" />
        </ExploreSection>
      </main>
    </div>
  );
}

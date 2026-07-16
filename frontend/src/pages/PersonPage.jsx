import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import BackLink from "../components/BackLink";
import { ROUTES } from "../lib/backNav.js";
import { getPerson } from "../api/client";
import { titleDetailPath } from "../lib/titleLinks.js";

const BIO_PREVIEW = 420;

function roleLabel(item) {
  const character = String(item?.character || "").trim();
  if (character) return character;
  const job = String(item?.job || "").trim();
  if (job) return job;
  const department = String(item?.department || "").trim();
  return department || null;
}

export default function PersonPage() {
  const { tmdbPersonId } = useParams();
  const [person, setPerson] = useState(null);
  const [error, setError] = useState("");
  const [bioExpanded, setBioExpanded] = useState(false);

  useEffect(() => {
    setPerson(null);
    setError("");
    setBioExpanded(false);
    getPerson(tmdbPersonId)
      .then(setPerson)
      .catch((err) => setError(err.message || "Could not load person."));
  }, [tmdbPersonId]);

  if (error) {
    return (
      <div className="app-root person-page" data-testid="person-page">
        <header className="browse-page-header">
          <BackLink fallbackTo={ROUTES.explore} />
        </header>
        <p className="error">{error}</p>
      </div>
    );
  }

  if (!person) {
    return (
      <div className="app-root person-page" data-testid="person-page">
        <p className="title-detail-loading">Loading…</p>
      </div>
    );
  }

  const bio = String(person.biography || "").trim();
  const bioNeedsTruncate = bio.length > BIO_PREVIEW;
  const bioShown =
    bio && bioNeedsTruncate && !bioExpanded ? `${bio.slice(0, BIO_PREVIEW).trim()}…` : bio;
  const titles = Array.isArray(person.titles) ? person.titles : [];

  return (
    <div className="app-root person-page" data-testid="person-page">
      <header className="browse-page-header">
        <BackLink fallbackTo={ROUTES.explore} />
        <Link to="/explore" className="app-topbar-link">
          Explore
        </Link>
      </header>

      <section className="person-hero" data-testid="person-hero">
        <div className="person-hero-media">
          {person.profile_url ? (
            <img src={person.profile_url} alt="" className="person-profile-image" />
          ) : (
            <div className="person-profile-fallback" aria-hidden="true">
              {(person.name || "?").slice(0, 1)}
            </div>
          )}
        </div>
        <div className="person-hero-copy">
          <p className="person-eyebrow">
            {person.known_for_department || "In your library"}
          </p>
          <h1 data-testid="person-name">{person.name || "Unknown"}</h1>
          {(person.birthday || person.place_of_birth) && (
            <p className="person-vital">
              {[person.birthday, person.place_of_birth].filter(Boolean).join(" · ")}
              {person.deathday ? ` — ${person.deathday}` : ""}
            </p>
          )}
          {bioShown ? (
            <div className="person-bio" data-testid="person-bio">
              <p>{bioShown}</p>
              {bioNeedsTruncate ? (
                <button
                  type="button"
                  className="ghost person-bio-toggle"
                  data-testid="person-bio-toggle"
                  onClick={() => setBioExpanded((open) => !open)}
                >
                  {bioExpanded ? "Show less" : "Read more"}
                </button>
              ) : null}
            </div>
          ) : (
            <p className="status status-secondary">No biography available from TMDB.</p>
          )}
        </div>
      </section>

      <section className="person-library" data-testid="person-library">
        <header className="browse-section-header">
          <h2>In your library</h2>
          <p className="explore-section-subtitle">
            {titles.length
              ? `${titles.length} title${titles.length === 1 ? "" : "s"} linked via credits`
              : "No library titles linked to this person yet"}
          </p>
        </header>
        {titles.length ? (
          <div className="explore-poster-wall person-title-grid">
            {titles.map((item) => {
              const path = titleDetailPath({ ...item, in_library: true });
              const role = roleLabel(item);
              const key = `${item.media_type}-${item.tmdb_id || item.rating_key || item.title}-${role || ""}`;
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
                  {role ? <p className="explore-card-meta explore-card-context">{role}</p> : null}
                </>
              );
              return (
                <article key={key} className="explore-cinema-card" data-testid="person-title-card">
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
        ) : (
          <p className="explore-empty status status-secondary" data-testid="person-library-empty">
            Their biography is here, but nothing in your shelves is credited to them yet.
          </p>
        )}
      </section>
    </div>
  );
}

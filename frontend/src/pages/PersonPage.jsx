import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import BackLink from "../components/BackLink";
import LibraryMediaCard from "../components/LibraryMediaCard";
import { getPerson } from "../api/client";
import AppShell from "../layouts/AppShell";
import { ROUTES } from "../lib/backNav.js";
import {
  filterPersonTitles,
  groupPersonTitles,
  libraryOwnedPercent,
} from "../lib/personBrowse.js";

const BIO_PREVIEW = 420;

const ROLE_FILTERS = [
  { id: "all", label: "All" },
  { id: "cast", label: "Cast" },
  { id: "director", label: "Director" },
];

export default function PersonPage() {
  const { tmdbPersonId } = useParams();
  const [person, setPerson] = useState(null);
  const [error, setError] = useState("");
  const [bioExpanded, setBioExpanded] = useState(false);
  const [roleFilter, setRoleFilter] = useState("all");

  useEffect(() => {
    setPerson(null);
    setError("");
    setBioExpanded(false);
    setRoleFilter("all");
    getPerson(tmdbPersonId)
      .then(setPerson)
      .catch((err) => setError(err.message || "Could not load person."));
  }, [tmdbPersonId]);

  const titles = useMemo(
    () => groupPersonTitles(filterPersonTitles(person?.titles, roleFilter)),
    [person, roleFilter],
  );
  const owned = person ? libraryOwnedPercent(person) : null;

  if (error) {
    return (
      <AppShell
        className="app-root person-page"
        testId="person-page"
        variant="browse"
        leading={<BackLink fallbackTo={ROUTES.explore} />}
      >
        <p className="error">{error}</p>
      </AppShell>
    );
  }

  if (!person) {
    return (
      <AppShell
        className="app-root person-page"
        testId="person-page"
        variant="browse"
        leading={<BackLink fallbackTo={ROUTES.explore} />}
      >
        <p className="title-detail-loading">Loading…</p>
      </AppShell>
    );
  }

  const bio = String(person.biography || "").trim();
  const bioNeedsTruncate = bio.length > BIO_PREVIEW;
  const bioShown =
    bio && bioNeedsTruncate && !bioExpanded ? `${bio.slice(0, BIO_PREVIEW).trim()}…` : bio;

  return (
    <AppShell
      className="app-root person-page"
      testId="person-page"
      variant="browse"
      leading={<BackLink fallbackTo={ROUTES.explore} />}
      actions={
        <Link to="/explore" className="app-topbar-link">
          Explore
        </Link>
      }
    >
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
          {owned ? (
            <p className="person-owned-pct" data-testid="person-owned-pct">
              {owned.label}
              <span className="person-owned-detail">
                {" "}
                ({owned.owned} of {owned.total})
              </span>
            </p>
          ) : person.in_library_count != null ? (
            <p className="person-owned-pct" data-testid="person-owned-count">
              {person.in_library_count} title
              {person.in_library_count === 1 ? "" : "s"} in your library
            </p>
          ) : null}
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
              ? `${titles.length} title${titles.length === 1 ? "" : "s"}${
                  roleFilter === "all" ? " linked via credits" : ` as ${roleFilter}`
                }`
              : "No library titles linked to this person yet"}
          </p>
        </header>

        <div
          className="person-role-filters"
          role="tablist"
          aria-label="Credit role"
          data-testid="person-role-filters"
        >
          {ROLE_FILTERS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={roleFilter === tab.id}
              className={`explore-media-tab${roleFilter === tab.id ? " is-active" : ""}`}
              data-testid={`person-role-${tab.id}`}
              onClick={() => setRoleFilter(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {titles.length ? (
          <div className="explore-poster-wall person-title-grid">
            {titles.map((item) => {
              const credits = Array.isArray(item.credits) ? item.credits : [];
              const key = `${item.media_type}-${item.tmdb_id || item.rating_key || item.title}`;
              return (
                <div key={key} className="person-title-card-wrap">
                  <LibraryMediaCard
                    item={{ ...item, in_library: true }}
                    testId="person-title-card"
                  />
                  {credits.length ? (
                    <ul className="person-credit-list" data-testid="person-credit-list">
                      {credits.map((credit) => (
                        <li
                          key={credit}
                          className="explore-card-meta explore-card-context person-credit"
                        >
                          {credit}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              );
            })}
          </div>
        ) : (
          <p className="explore-empty status status-secondary" data-testid="person-library-empty">
            {roleFilter === "all"
              ? "Their biography is here, but nothing in your shelves is credited to them yet."
              : `No ${roleFilter} credits in your library for this person.`}
          </p>
        )}
      </section>
    </AppShell>
  );
}

import { useEffect, useState } from "react";
import LibraryMediaCard from "./LibraryMediaCard";
import {
  SURPRISE_SECTION_INTRO,
  SURPRISE_SHOWCASE_INITIAL,
  buildSurpriseWhy,
  visibleSurpriseItems,
} from "../lib/surpriseNeighbors.js";

/**
 * Showcase grid for Plot Lab surprising neighbors — featured lead + why copy.
 */
export default function SurprisingNeighborsShowcase({
  items,
  loading,
  seedGenres = [],
  showIntro = true,
  testId = "explore-neighbors-rail",
  seedItemId = null,
  onDismissNeighbor = null,
  dismissBusyId = null,
}) {
  const [expanded, setExpanded] = useState(false);
  const seedKey = Array.isArray(items)
    ? items.map((item) => item?.id || item?.rating_key || item?.title).join("|")
    : "";

  useEffect(() => {
    setExpanded(false);
  }, [seedKey]);

  if (loading) {
    return <p className="status status-secondary">Loading surprising neighbors…</p>;
  }
  if (!items?.length) return null;

  const visible = visibleSurpriseItems(items, {
    expanded,
    initial: SURPRISE_SHOWCASE_INITIAL,
  });
  const hiddenCount = Math.max(0, items.length - visible.length);
  const [featured, ...rest] = visible;
  const featuredWhy = buildSurpriseWhy(featured, { seedGenres });

  return (
    <div className="surprise-showcase" data-testid={testId}>
      {showIntro ? (
        <p className="surprise-showcase-intro" data-testid={`${testId}-intro`}>
          {SURPRISE_SECTION_INTRO}
        </p>
      ) : null}

      {featured ? (
        <article
          className="surprise-showcase-featured"
          data-testid={`${testId}-featured`}
        >
          <div className="surprise-showcase-featured-card">
            <LibraryMediaCard
              item={featured}
              showRecommend={false}
              testId={`${testId}-featured-card`}
            />
          </div>
          <div className="surprise-showcase-featured-why">
            <p className="surprise-showcase-eyebrow">Why this neighbor</p>
            <h4 className="surprise-showcase-headline">
              {featuredWhy?.headline || "Surprising plot neighbor"}
            </h4>
            {featuredWhy?.signals?.length ? (
              <ul className="surprise-showcase-signals" data-testid={`${testId}-featured-why`}>
                {featuredWhy.signals.map((signal) => (
                  <li key={signal}>{signal}</li>
                ))}
              </ul>
            ) : (
              <p className="surprise-showcase-detail status status-secondary">
                High plot similarity with lower genre/keyword/credit overlap than
                obvious shelfmates.
              </p>
            )}
          </div>
        </article>
      ) : null}

      {rest.length ? (
        <div className="surprise-showcase-grid" data-testid={`${testId}-grid`}>
          {rest.map((item) => {
            const why = buildSurpriseWhy(item, { seedGenres });
            return (
              <div
                key={item.id || item.rating_key || item.title}
                className="surprise-showcase-cell"
              >
                <LibraryMediaCard
                  item={item}
                  meta={why?.headline || null}
                  showRecommend={false}
                />
                {why?.detail ? (
                  <p className="surprise-showcase-cell-why" data-testid={`${testId}-why`}>
                    {why.detail}
                  </p>
                ) : null}
                {onDismissNeighbor && seedItemId && item?.id ? (
                  <button
                    type="button"
                    className="ghost surprise-showcase-dismiss"
                    disabled={dismissBusyId === item.id}
                    data-testid={`${testId}-dismiss-${item.id}`}
                    onClick={() => onDismissNeighbor(item)}
                  >
                    Not a neighbor
                  </button>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : null}

      {hiddenCount > 0 || expanded ? (
        <div className="surprise-showcase-more">
          <button
            type="button"
            className="ghost"
            data-testid={`${testId}-show-more`}
            onClick={() => setExpanded((prev) => !prev)}
          >
            {expanded ? "Show fewer" : `Show ${hiddenCount} more`}
          </button>
        </div>
      ) : null}
    </div>
  );
}

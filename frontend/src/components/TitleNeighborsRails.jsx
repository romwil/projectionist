import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { getTitleRelations } from "../api/client";
import { relationWhyCopy, relatedTitlesPath } from "../lib/relationUx.js";
import { titleDetailPath } from "../lib/titleLinks.js";
import PosterOverlayControls from "./PosterOverlayControls";
import TitleDetailLink from "./TitleDetailLink";

function TitleNeighborCard({ item, testId, why = null }) {
  const libraryItem = { ...item, in_library: true };
  const path = titleDetailPath(libraryItem);
  const poster = libraryItem.poster_url ? (
    <img src={libraryItem.poster_url} alt="" loading="lazy" />
  ) : (
    <div className="poster-fallback">{libraryItem.title?.slice(0, 1) || "?"}</div>
  );

  return (
    <article className="title-neighbor-card" data-testid={testId}>
      <div className="title-neighbor-poster">
        {path ? (
          <TitleDetailLink item={libraryItem} className="title-neighbor-poster-link">
            {poster}
          </TitleDetailLink>
        ) : (
          poster
        )}
        <PosterOverlayControls item={libraryItem} testPrefix="title-neighbor" />
      </div>
      <h3>
        {path ? <TitleDetailLink item={libraryItem}>{libraryItem.title}</TitleDetailLink> : libraryItem.title}
      </h3>
      {libraryItem.year ? <p className="title-neighbor-year">{libraryItem.year}</p> : null}
      {why?.label ? (
        <p className="title-neighbor-why" data-testid={`${testId}-why`}>
          {why.label}
          {why.detail ? <span className="title-neighbor-why-detail"> · {why.detail}</span> : null}
        </p>
      ) : null}
    </article>
  );
}

/**
 * Collection / crew / More-like-this poster rails.
 * Used on the full title page and the phone title sheet.
 */
export default function TitleNeighborsRails({
  mediaType,
  itemId,
  idType = "tmdb",
  detail,
  showConnectionsEntry = false,
  compact = false,
}) {
  const [relations, setRelations] = useState(null);
  const [neighborMode, setNeighborMode] = useState("similar");
  const carouselRef = useRef(null);

  useEffect(() => {
    if (!mediaType || !itemId) {
      setRelations([]);
      return undefined;
    }
    let cancelled = false;
    getTitleRelations(mediaType, itemId, { idType, limit: 50 })
      .then((data) => {
        if (!cancelled) setRelations(Array.isArray(data?.items) ? data.items : []);
      })
      .catch(() => {
        if (!cancelled) setRelations([]);
      });
    return () => {
      cancelled = true;
    };
  }, [mediaType, itemId, idType]);

  const collectionEdges = (relations || []).filter((edge) => edge.relation === "collection");
  const crewEdges = (relations || []).filter((edge) => edge.relation === "shared_crew");
  const plotEdges = (relations || []).filter((edge) => edge.relation === "neighbor");
  const neighbors =
    neighborMode === "surprising"
      ? plotEdges.filter((edge) => edge.why?.surprise_flavor)
      : plotEdges;
  const showNeighbors = plotEdges.length > 0;
  const relatedPath = relatedTitlesPath(detail);

  function scrollCarousel(dir) {
    const node = carouselRef.current;
    if (!node) return;
    node.scrollBy({ left: dir * 320, behavior: "smooth" });
  }

  if (relations === null) {
    return compact ? (
      <p className="title-neighbors-intro" data-testid="title-neighbors-loading">
        Loading more like this…
      </p>
    ) : null;
  }

  return (
    <>
      {showConnectionsEntry ? (
        <section className="title-relations-entry" data-testid="title-relations-entry">
          <div>
            <h2>Title connections</h2>
            <p>Follow this title through collections, shared filmmakers, and plot kinship.</p>
          </div>
          <Link to={relatedPath} className="title-cta title-cta-ghost title-relations-cta">
            Related titles
            <span className="material-symbols-outlined" aria-hidden="true">
              arrow_forward
            </span>
          </Link>
        </section>
      ) : null}

      {showConnectionsEntry && !relations.length ? (
        <p className="title-relations-cold-note status status-secondary">
          Connections are still warming up for this title. The background library refresh may
          add them later.
        </p>
      ) : null}

      {collectionEdges.length ? (
        <section className="title-neighbors title-collection-rail" data-testid="title-collection-rail">
          <div className="title-neighbors-header">
            <h2>
              More in{" "}
              {detail?.collection_name ||
                collectionEdges[0]?.why?.collection_name ||
                "this collection"}
            </h2>
          </div>
          <div className="title-neighbors-track">
            {collectionEdges.map((edge) => (
              <TitleNeighborCard
                key={`${edge.relation}-${edge.to_id}`}
                item={edge.peer}
                testId="title-collection-peer"
                why={relationWhyCopy(edge.why)}
              />
            ))}
          </div>
        </section>
      ) : null}

      {crewEdges.length ? (
        <section className="title-neighbors title-crew-rail" data-testid="title-crew-rail">
          <div className="title-neighbors-header">
            <h2>Shared cast &amp; crew</h2>
          </div>
          <div className="title-neighbors-track">
            {crewEdges.map((edge) => (
              <TitleNeighborCard
                key={`${edge.relation}-${edge.to_id}`}
                item={edge.peer}
                testId="title-crew-peer"
                why={relationWhyCopy(edge.why)}
              />
            ))}
          </div>
        </section>
      ) : null}

      {showNeighbors ? (
        <section
          className={`title-neighbors${neighborMode === "surprising" ? " title-neighbors--surprising" : ""}`}
          data-testid="title-neighbors"
        >
          <div className="title-neighbors-header">
            <h2>
              {compact
                ? "More like this"
                : neighborMode === "surprising"
                  ? "Surprisingly similar"
                  : "Similar plot"}
            </h2>
            <div className="title-neighbors-controls">
              <div className="title-neighbors-modes" role="group" aria-label="Neighbor ranking">
                <button
                  type="button"
                  className={`ghost title-neighbors-mode${neighborMode === "similar" ? " is-active" : ""}`}
                  data-testid="title-neighbors-similar"
                  aria-pressed={neighborMode === "similar"}
                  onClick={() => setNeighborMode("similar")}
                >
                  Similar
                </button>
                <button
                  type="button"
                  className={`ghost title-neighbors-mode${neighborMode === "surprising" ? " is-active" : ""}`}
                  data-testid="title-neighbors-surprising"
                  aria-pressed={neighborMode === "surprising"}
                  onClick={() => setNeighborMode("surprising")}
                >
                  Surprising
                </button>
              </div>
              <button
                type="button"
                className="ghost title-neighbors-nav"
                aria-label="Scroll left"
                onClick={() => scrollCarousel(-1)}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  chevron_left
                </span>
              </button>
              <button
                type="button"
                className="ghost title-neighbors-nav"
                aria-label="Scroll right"
                onClick={() => scrollCarousel(1)}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  chevron_right
                </span>
              </button>
            </div>
          </div>
          {neighborMode === "surprising" ? (
            <p className="title-neighbors-intro" data-testid="title-neighbors-surprise-intro">
              Strong plot kinship with little overlap in genre, keyword, or filmmaker labels.
            </p>
          ) : null}
          {neighborMode === "surprising" && !neighbors.length ? (
            <p className="title-neighbors-intro">
              No surprising connection is ready yet. Similar plot matches are still available.
            </p>
          ) : null}
          <div className="title-neighbors-track" ref={carouselRef}>
            {neighbors.map((edge) => (
              <TitleNeighborCard
                key={`${edge.relation}-${edge.to_id}`}
                item={edge.peer}
                testId="title-neighbor-card"
                why={relationWhyCopy(edge.why)}
              />
            ))}
          </div>
        </section>
      ) : compact ? (
        <p className="title-neighbors-intro" data-testid="title-neighbors-empty">
          More like this is still warming up for this title.
        </p>
      ) : null}
    </>
  );
}

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { formatMatchLayers } from "../lib/plotKnowledge.js";
import { titleDetailPath } from "../lib/titleLinks.js";
import PosterOverlayControls from "./PosterOverlayControls";

/**
 * Explore / tag / plot-lab poster card with hover Watch / Trailer / Recommend.
 */
export default function LibraryMediaCard({
  item,
  meta,
  onSeed,
  seedLabel = "Surprise from this",
  onRecommend,
  showRecommend = false,
  onOpenDetail,
  motifWhy = null,
  onTogglePin,
  pinned = false,
  testId = "explore-title-card",
}) {
  const [hovered, setHovered] = useState(false);
  const [whyOpen, setWhyOpen] = useState(false);
  // Browse/feed endpoints are library-only but some compact payloads omit
  // in_library. A Plex rating key is the required proof for playable posters.
  const libraryItem = {
    ...item,
    in_library: item?.in_library ?? Boolean(item?.rating_key || item?.plex_rating_key),
  };

  const path = titleDetailPath(libraryItem);

  useEffect(() => {
    setWhyOpen(false);
  }, [item?.id, item?.rating_key, motifWhy?.summary]);

  const media = item.poster_url ? (
    <img src={item.poster_url} alt="" loading="lazy" />
  ) : (
    <div className="poster-fallback">{libraryItem.title?.slice(0, 1) || "?"}</div>
  );

  const titleBlock = (
    <>
      <h3>{item.title || "Untitled"}</h3>
      {item.year ? <p className="explore-card-meta">{item.year}</p> : null}
      {meta ? <p className="explore-card-meta explore-card-context">{meta}</p> : null}
    </>
  );

  function handleOpenDetail(event) {
    if (!onOpenDetail) return;
    event.preventDefault();
    onOpenDetail(item, event);
  }

  const posterNode =
    path && onOpenDetail ? (
      <button
        type="button"
        className="explore-poster-link explore-poster-button"
        tabIndex={-1}
        aria-hidden="true"
        onClick={handleOpenDetail}
      >
        {media}
      </button>
    ) : path ? (
      <Link to={path} className="explore-poster-link" tabIndex={-1} aria-hidden="true">
        {media}
      </Link>
    ) : (
      media
    );

  const titleNode =
    path && onOpenDetail ? (
      <button type="button" className="explore-cinema-card-link explore-cinema-card-button" onClick={handleOpenDetail}>
        {titleBlock}
      </button>
    ) : path ? (
      <Link to={path} className="explore-cinema-card-link">
        {titleBlock}
      </Link>
    ) : (
      <div className="explore-cinema-card-link">{titleBlock}</div>
    );

  return (
    <article
      className={`explore-cinema-card${hovered ? " is-hovered" : ""}`}
      data-testid={testId}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className="explore-poster">
        {posterNode}
        <PosterOverlayControls
          item={libraryItem}
          onRecommend={onRecommend}
          showRecommend={showRecommend}
          onSeed={onSeed}
          onTogglePin={onTogglePin}
          pinned={pinned}
          motifWhy={motifWhy}
          testPrefix="explore"
        />
      </div>
      {titleNode}

      {onSeed && item.id != null ? (
        <button
          type="button"
          className="ghost explore-seed-btn"
          data-testid="explore-seed-btn"
          onClick={() => onSeed(item)}
        >
          {seedLabel}
        </button>
      ) : null}

      {motifWhy ? (
        <div className="explore-motif-why" data-testid="explore-motif-why">
          <button
            type="button"
            className="ghost explore-motif-why-btn"
            data-testid="explore-motif-why-btn"
            aria-expanded={whyOpen}
            onClick={() => setWhyOpen((open) => !open)}
          >
            {whyOpen ? "Hide why" : "Why?"}
          </button>
          {whyOpen ? (
            <div className="explore-motif-why-detail" data-testid="explore-motif-why-detail">
              <p>{motifWhy.summary}</p>
              {motifWhy.matchLayers?.length ? (
                <ul className="explore-motif-why-layers" data-testid="explore-motif-why-layers">
                  {motifWhy.matchLayers.map((entry) => (
                    <li key={`${entry.motif}-${entry.layers.join("-")}`}>
                      <strong>{entry.motif}</strong>
                      <span className="explore-motif-why-layer-labels">
                        {formatMatchLayers(entry.layers)}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : motifWhy.matched?.length ? (
                <p className="explore-motif-why-matched">
                  Motifs: {motifWhy.matched.join(" · ")}
                </p>
              ) : null}
              {motifWhy.excerpts?.length ? (
                <ul className="explore-motif-why-excerpts">
                  {motifWhy.excerpts.map((entry) => (
                    <li key={`${entry.motif}-${entry.excerpt}`}>
                      <strong>{entry.motif}</strong>
                      <span>{entry.excerpt}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

    </article>
  );
}

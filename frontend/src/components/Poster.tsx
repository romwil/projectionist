import { useEffect, useRef, useState, type CSSProperties } from "react";
import { posterMotif, posterPalette, posterSeed } from "../lib/posterPlaceholder";
import { cachedPosterMark, loadedPosterMark, posterIsShown } from "../lib/posterShown";

type PosterProps = {
  src?: string | null;
  title?: string | null;
  year?: string | number | null;
  itemId?: string | number | null;
  className?: string;
  /** Draw the title on the art. Shelves that put the title under the card leave this off. */
  titleOnArt?: boolean;
};

/**
 * Shelf and lockup art: a rim, a two-layer shadow, and a generated
 * placeholder under the cached image. Missing art is never a flat fill.
 */
export default function Poster({
  src,
  title,
  year,
  itemId,
  className,
  titleOnArt = false,
}: PosterProps) {
  const label = String(title || "").trim() || "Untitled";
  const seedKey = String(itemId ?? label);
  const seed = posterSeed(seedKey);
  const motif = posterMotif(seed);
  const paint = posterPalette(seed);
  const [loadedSrc, setLoadedSrc] = useState("");
  const art = String(src || "").trim();
  const shown = posterIsShown(art, loadedSrc);
  const imgRef = useRef<HTMLImageElement>(null);

  useEffect(() => {
    const mark = cachedPosterMark(art, imgRef.current);
    if (mark) setLoadedSrc(mark);
  }, [art]);

  const style = {
    "--poster-a": paint.a,
    "--poster-b": paint.b,
    "--poster-light": paint.light,
  } as CSSProperties;

  return (
    <div
      className={`poster poster-fallback${className ? ` ${className}` : ""}`}
      data-motif={motif}
      data-testid={art ? "poster" : "poster-missing-art"}
      role="img"
      aria-label={year ? `${label}, ${year}` : label}
      style={style}
    >
      <div className="poster-placeholder" aria-hidden={art ? true : undefined}>
        <span className="poster-light" />
        <span className={`poster-silhouette poster-silhouette--${motif}`} />
        {!art || !shown ? (
          <span className="poster-lockup">
            <span className="poster-fallback-title poster-lockup-title">{label}</span>
            {year ? <span className="poster-fallback-year poster-lockup-year">{year}</span> : null}
          </span>
        ) : null}
      </div>
      {art ? (
        <img
          ref={imgRef}
          key={art}
          src={art}
          alt=""
          aria-hidden="true"
          className={`poster-art${shown ? " is-shown" : ""}`}
          loading="lazy"
          onLoad={() => setLoadedSrc(loadedPosterMark(art))}
          onError={() => setLoadedSrc("")}
        />
      ) : null}
      {titleOnArt ? <span className="poster-scrim" aria-hidden="true" /> : null}
    </div>
  );
}

import Poster from "./Poster";

/**
 * Shelf art. Renders the shared Poster: a generated placeholder, then the
 * cached image fading in over it. `posterUrl` is only ever the URL our API
 * already returned.
 */
type PosterArtProps = {
  posterUrl?: string | null;
  title?: string | null;
  year?: string | number | null;
  itemId?: string | number | null;
  /** Kept so older call sites still type-check. The poster itself is one element. */
  as?: "div" | "span";
  className?: string;
  titleOnArt?: boolean;
};

export default function PosterArt({
  posterUrl,
  title,
  year,
  itemId,
  as: _as = "div",
  className,
  titleOnArt = false,
}: PosterArtProps) {
  void _as;
  return (
    <Poster
      src={posterUrl}
      title={title}
      year={year}
      itemId={itemId}
      className={className}
      titleOnArt={titleOnArt}
    />
  );
}

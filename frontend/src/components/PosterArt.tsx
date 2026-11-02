/**
 * VIS-027: real poster when we have one; otherwise a *designed* missing-art
 * state (title + year inside the 2:3 well) instead of a single oversized
 * initial letter. No open proxy — this only ever renders `poster_url` as
 * given by our own API payloads, or falls back to text we already have.
 */
type PosterArtProps = {
  posterUrl?: string | null;
  title?: string | null;
  year?: string | number | null;
  as?: "div" | "span";
  className?: string;
};

export default function PosterArt({
  posterUrl,
  title,
  year,
  as: Tag = "div",
  className,
}: PosterArtProps) {
  if (posterUrl) {
    return <img src={posterUrl} alt="" loading="lazy" className={className} />;
  }
  const label = String(title || "").trim() || "Untitled";
  return (
    <Tag
      className={`poster-fallback${className ? ` ${className}` : ""}`}
      data-testid="poster-missing-art"
    >
      <span className="poster-fallback-title">{label}</span>
      {year ? <span className="poster-fallback-year">{year}</span> : null}
    </Tag>
  );
}

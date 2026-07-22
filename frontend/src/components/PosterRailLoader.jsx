/**
 * Centered loading indicator for poster rails.
 * Reserves poster-row height so layout does not jump while titles load.
 */
export default function PosterRailLoader({
  label = "Loading titles…",
  testId = "poster-rail-loader",
}) {
  return (
    <div
      className="poster-rail-loader"
      data-testid={testId}
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="poster-rail-loader-inner">
        <span className="poster-rail-loader-spinner" aria-hidden="true" />
        <p className="poster-rail-loader-label">{label}</p>
      </div>
    </div>
  );
}

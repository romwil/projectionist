const PENDING_CARDS = 8;

type BrowseResultsRegionProps = {
  testId?: string;
  className?: string;
  loading?: boolean;
  error?: React.ReactNode;
  hasItems?: boolean;
  empty?: React.ReactNode;
  children?: React.ReactNode;
};

/**
 * Poster-grid results slot.
 * A request that already has titles stays quiet — year/genre/language catalogs
 * and a follow-up library query must not paint a second "Loading…" line over
 * posters. An empty grid that is still waiting gets a label and poster skeletons
 * in this region only, so the browse bar above stays put.
 */
export default function BrowseResultsRegion({
  testId,
  className = "explore-section-results",
  loading = false,
  error = "",
  hasItems = false,
  empty = null,
  children = null,
}: BrowseResultsRegionProps) {
  const waiting = Boolean(loading) && !hasItems && !error;
  return (
    <section className={className} data-testid={testId}>
      {error ? <p className="error">{error}</p> : null}
      {waiting ? <BrowseGridPending /> : null}
      {!loading && !error && !hasItems ? empty : null}
      {hasItems ? children : null}
    </section>
  );
}

function BrowseGridPending() {
  return (
    <div
      className="browse-grid-pending"
      role="status"
      aria-live="polite"
      aria-busy="true"
      data-testid="browse-grid-pending"
    >
      <p className="browse-grid-pending-label" data-testid="browse-grid-pending-label">
        Loading titles
      </p>
      <div className="browse-grid-pending-wall" aria-hidden="true">
        {Array.from({ length: PENDING_CARDS }, (_, index: number) => (
          <div
            key={index}
            className="browse-grid-pending-card"
            data-testid="browse-grid-pending-card"
          />
        ))}
      </div>
    </div>
  );
}

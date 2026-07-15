export default function LibraryGlanceCard({ snapshot, onDismiss }) {
  if (!snapshot) return null;

  const { total, movies, shows, top_genres, decade_range, hidden_gems } = snapshot;

  return (
    <section className="library-glance-card" data-testid="library-glance-card">
      <header className="library-glance-header">
        <h4>Your Library at a Glance</h4>
        {onDismiss ? (
          <button
            type="button"
            className="ghost library-glance-dismiss"
            onClick={onDismiss}
            aria-label="Dismiss"
          >
            ×
          </button>
        ) : null}
      </header>
      <div className="library-glance-stats">
        <div className="library-glance-stat">
          <span className="library-glance-stat-value">{total}</span>
          <span className="library-glance-stat-label">Titles</span>
        </div>
        <div className="library-glance-stat">
          <span className="library-glance-stat-value">{movies}</span>
          <span className="library-glance-stat-label">Movies</span>
        </div>
        <div className="library-glance-stat">
          <span className="library-glance-stat-value">{shows}</span>
          <span className="library-glance-stat-label">Shows</span>
        </div>
        {hidden_gems > 0 ? (
          <div className="library-glance-stat highlight">
            <span className="library-glance-stat-value">{hidden_gems}</span>
            <span className="library-glance-stat-label">Hidden Gems</span>
          </div>
        ) : null}
      </div>
      <div className="library-glance-details">
        {top_genres?.length ? (
          <p className="library-glance-genres">
            Top genres: {top_genres.map((g) => g.name).join(", ")}
          </p>
        ) : null}
        {decade_range ? (
          <p className="library-glance-decades">Spanning {decade_range}</p>
        ) : null}
      </div>
    </section>
  );
}

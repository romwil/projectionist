export default function WatchlistSettingsPage() {
  return (
    <section className="settings-section" data-testid="settings-watchlist">
      <header className="settings-section-header">
        <h2>Watchlist</h2>
        <p>
          Pins already live in chat. Sync with your Plex Discover watchlist — pull on login, push on
          pin — arrives in a follow-on release.
        </p>
      </header>
      <div className="settings-placeholder" data-testid="watchlist-sync-placeholder">
        <p className="status status-secondary">
          Sync status and push/pull toggles will appear here once Plex watchlist sync is enabled.
        </p>
      </div>
    </section>
  );
}

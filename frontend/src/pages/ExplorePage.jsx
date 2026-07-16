import { Link } from "react-router-dom";

export default function ExplorePage() {
  return (
    <div className="app-root explore-stub" data-testid="explore-page">
      <header className="app-topbar">
        <div className="app-topbar-brand">
          <div className="app-topbar-titles">
            <h1>Explore</h1>
            <p className="app-topbar-eyebrow">Coming soon</p>
          </div>
        </div>
      </header>
      <main className="explore-stub-main">
        <p className="status status-secondary">
          Browse and discovery lands in a later wave. Use chat for recommendations for now.
        </p>
        <Link to="/" className="app-topbar-link">
          Back to chat
        </Link>
      </main>
    </div>
  );
}

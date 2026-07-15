import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <div className="not-found-page" data-testid="not-found-page">
      <div className="not-found-card">
        <p className="eyebrow">CuratorX</p>
        <h1>Page not found</h1>
        <p className="not-found-lede">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <Link to="/" className="not-found-home">
          Back to chat
        </Link>
      </div>
    </div>
  );
}

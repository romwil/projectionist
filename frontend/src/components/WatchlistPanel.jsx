import { Link } from "react-router-dom";
import { ROUTES } from "../lib/backNav.js";

/** Sidebar link to the full watchlist browse page. */
export default function WatchlistPanel({ count = 0 }) {
  if (!count) {
    return (
      <Link
        to={ROUTES.watchlist}
        className="watchlist-panel-toggle ghost sidebar-bottom-link"
        data-testid="watchlist-panel-toggle"
      >
        Watchlist
      </Link>
    );
  }

  return (
    <Link
      to={ROUTES.watchlist}
      className="watchlist-panel-toggle ghost sidebar-bottom-link"
      data-testid="watchlist-panel-toggle"
    >
      Watchlist ({count})
    </Link>
  );
}

import { Link } from "react-router-dom";
import { ROUTES } from "../lib/backNav.js";

/** Sidebar link to the full watchlist browse page. */
type WatchlistPanelProps = {
  count?: number;
};

export default function WatchlistPanel({ count = 0 }: WatchlistPanelProps) {
  return (
    <Link
      to={ROUTES.watchlist}
      className="sidebar-nav-btn"
      data-testid="watchlist-panel-toggle"
    >
      {count ? `Watchlist (${count})` : "Watchlist"}
    </Link>
  );
}

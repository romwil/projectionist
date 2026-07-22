import { Link } from "react-router-dom";
import { formatUnreadBadge } from "../lib/recommendationInbox.js";
import { ROUTES } from "../lib/backNav.js";

/**
 * Top-chrome inbox entry with unread badge.
 * Navigates to /inbox (primary destination for notifications).
 */
export default function InboxBadgeButton({
  unreadCount = 0,
  to = ROUTES.inbox,
  className = "app-topbar-icon inbox-badge-btn",
  active = false,
}) {
  const badge = formatUnreadBadge(unreadCount);
  return (
    <Link
      to={to}
      className={`${className}${active ? " is-active" : ""}`.replace(" is-active is-active", " is-active")}
      data-testid="topbar-inbox-button"
      aria-label={badge ? `Inbox, ${unreadCount} unread` : "Inbox"}
      aria-current={active ? "page" : undefined}
      data-tooltip={badge ? `Inbox (${badge})` : "Inbox"}
    >
      <span className="material-symbols-outlined" aria-hidden="true">
        notifications
      </span>
      {badge ? (
        <span className="inbox-unread-badge" data-testid="topbar-inbox-badge">
          {badge}
        </span>
      ) : null}
    </Link>
  );
}

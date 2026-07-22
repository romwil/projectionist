import { formatUnreadBadge } from "../lib/recommendationInbox.js";

/**
 * Top-chrome inbox entry with unread badge.
 * Scrolls to #notifications-inbox when items are present; otherwise focuses the inbox region.
 */
export default function InboxBadgeButton({
  unreadCount = 0,
  onOpen,
}) {
  const badge = formatUnreadBadge(unreadCount);
  return (
    <button
      type="button"
      className="app-topbar-icon inbox-badge-btn"
      data-testid="topbar-inbox-button"
      aria-label={badge ? `Inbox, ${unreadCount} unread` : "Inbox"}
      data-tooltip={badge ? `Inbox (${badge})` : "Inbox"}
      onClick={onOpen}
    >
      <span className="material-symbols-outlined" aria-hidden="true">
        notifications
      </span>
      {badge ? (
        <span className="inbox-unread-badge" data-testid="topbar-inbox-badge">
          {badge}
        </span>
      ) : null}
    </button>
  );
}

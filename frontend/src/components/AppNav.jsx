import { createPortal } from "react-dom";
import { Link, useLocation } from "react-router-dom";
import { buildAppNavItems } from "../lib/appNavItems.js";
import { ROUTES, watchlistBrowseHref } from "../lib/backNav.js";
import { isPrimaryNavActive } from "../lib/primaryNav.js";
import { useAnchoredPopover } from "../hooks/useAnchoredPopover";

export default function AppNav({
  open,
  onClose,
  isOwner = false,
  showSettings = true,
  isYouth = false,
  role = "owner",
  multiUserEnabled = true,
  authReady = true,
  liveChannelsReady = false,
  adminBadges = null,
}) {
  const location = useLocation();
  const { rootRef: panelRef } = useAnchoredPopover({
    open,
    onOpenChange: (next) => {
      if (!next) onClose?.();
    },
    closeOnEscape: true,
  });

  if (!open) return null;

  const items = buildAppNavItems({
    isOwner,
    showSettings,
    isYouth,
    role,
    pathname: location.pathname,
    multiUserEnabled,
    authReady,
    liveChannelsReady,
  });
  const badgeValue = adminBadges || {};

  function handleWatchlistClick() {
    onClose?.();
  }

  function badgeCount(item) {
    if (!item?.badge) return null;
    const count = badgeValue[item.badge];
    return typeof count === "number" && count > 0 ? count : null;
  }

  return createPortal(
    <div className="app-nav-layer" data-testid="app-nav-layer">
      <button
        type="button"
        className="app-nav-backdrop"
        aria-label="Close navigation"
        data-testid="app-nav-backdrop"
        onClick={onClose}
      />
      <nav
        ref={panelRef}
        className="app-nav-drawer"
        data-testid="app-nav-drawer"
        aria-label="Primary"
      >
        <div className="app-nav-header">
          <p className="eyebrow">Menu</p>
          <button
            type="button"
            className="ghost app-nav-close"
            data-testid="app-nav-close"
            aria-label="Close menu"
            onClick={onClose}
          >
            ✕
          </button>
        </div>
        <ul className="app-nav-list">
          {items.map((item) => {
            if (item.kind === "heading") {
              return (
                <li key={item.id} className="app-nav-heading-item" role="presentation">
                  <p className="app-nav-heading eyebrow" data-testid={item.testId || `app-nav-${item.id}`}>
                    {item.label}
                  </p>
                </li>
              );
            }
            if (item.kind === "watchlist") {
              return (
                <li key={item.id}>
                  <Link
                    to={watchlistBrowseHref()}
                    className="app-nav-link"
                    data-testid={item.testId}
                    onClick={handleWatchlistClick}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            }
            const active =
              item.kind === "primary" || item.id === "chat" || item.to === ROUTES.chat
                ? isPrimaryNavActive(item, location.pathname)
                : location.pathname === item.to || location.pathname.startsWith(`${item.to}/`);
            const count = badgeCount(item);
            return (
              <li key={item.id}>
                <Link
                  to={item.to}
                  className={`app-nav-link${active ? " is-active" : ""}${count != null ? " app-nav-link-badged" : ""}`}
                  data-testid={item.testId}
                  onClick={onClose}
                >
                  <span>{item.label}</span>
                  {count != null ? (
                    <span
                      className="app-nav-badge"
                      data-testid={`${item.testId}-badge`}
                      aria-label={`${count} open`}
                    >
                      {count > 99 ? "99+" : count}
                    </span>
                  ) : null}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>,
    document.body,
  );
}

export function AppNavToggle({ open, onClick, testId = "app-nav-toggle" }) {
  return (
    <button
      type="button"
      className="app-nav-toggle ghost"
      data-testid={testId}
      aria-label="Open navigation menu"
      aria-expanded={open}
      onClick={onClick}
    >
      <span aria-hidden="true">☰</span>
    </button>
  );
}

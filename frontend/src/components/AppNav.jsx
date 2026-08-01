import { createPortal } from "react-dom";
import { Link, useLocation } from "react-router-dom";
import { buildAppNavItems } from "../lib/appNavItems.js";
import { ROUTES, watchlistBrowseHref } from "../lib/backNav.js";
import { isPrimaryNavActive } from "../lib/primaryNav.js";
import { useAnchoredPopover } from "../hooks/useAnchoredPopover";

function isAdminGroupHeading(item) {
  return item?.kind === "heading" && String(item.id || "").startsWith("admin-heading-");
}

function adminGroupClass(item) {
  const id = String(item?.id || "");
  if (id.endsWith("-home")) return "app-nav-admin-group-home";
  if (id.endsWith("-household")) return "app-nav-admin-group-household";
  if (id.endsWith("-ops")) return "app-nav-admin-group-ops";
  return "";
}

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

  function renderLinkItem(item) {
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
  }

  const rendered = [];
  for (let index = 0; index < items.length; index += 1) {
    const item = items[index];
    if (isAdminGroupHeading(item)) {
      const links = [];
      let cursor = index + 1;
      while (cursor < items.length && items[cursor].kind === "admin") {
        links.push(items[cursor]);
        cursor += 1;
      }
      rendered.push(
        <li
          key={item.id}
          className={`app-nav-admin-group ${adminGroupClass(item)}`.trim()}
          role="presentation"
          data-testid={`app-nav-group-${item.id}`}
        >
          <div className="app-nav-admin-group-band">
            <p
              className="app-nav-heading app-nav-heading-side"
              data-testid={item.testId || `app-nav-${item.id}`}
            >
              {item.label}
            </p>
            <ul className="app-nav-admin-group-links">{links.map((link) => renderLinkItem(link))}</ul>
          </div>
        </li>,
      );
      index = cursor - 1;
      continue;
    }
    if (item.kind === "heading") {
      rendered.push(
        <li key={item.id} className="app-nav-heading-item" role="presentation">
          <p className="app-nav-heading eyebrow" data-testid={item.testId || `app-nav-${item.id}`}>
            {item.label}
          </p>
        </li>,
      );
      continue;
    }
    rendered.push(renderLinkItem(item));
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
        <ul className="app-nav-list">{rendered}</ul>
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

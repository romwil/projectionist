import { createPortal } from "react-dom";
import { Link, useLocation } from "react-router-dom";
import { buildAppNavItems } from "../lib/appNavItems.js";
import { ROUTES, watchlistBrowseHref } from "../lib/backNav.js";
import { useAnchoredPopover } from "../hooks/useAnchoredPopover";

export default function AppNav({
  open,
  onClose,
  isOwner = false,
  showSettings = true,
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

  const items = buildAppNavItems({ isOwner, showSettings });

  function handleWatchlistClick() {
    onClose?.();
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
          <p className="eyebrow">Navigate</p>
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
              item.to === ROUTES.chat
                ? location.pathname === "/"
                : location.pathname === item.to || location.pathname.startsWith(`${item.to}/`);
            return (
              <li key={item.id}>
                <Link
                  to={item.to}
                  className={`app-nav-link${active ? " is-active" : ""}`}
                  data-testid={item.testId}
                  onClick={onClose}
                >
                  {item.label}
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

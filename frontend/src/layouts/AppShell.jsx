import { useState } from "react";
import AppNav, { AppNavToggle } from "../components/AppNav";
import { useAuthGate } from "../components/UserMenu";

/**
 * Shared chrome for authenticated browse / detail routes.
 * Always provides hamburger AppNav; leaf pages pass BackLink via `leading` or `actions`.
 *
 * Variants:
 * - topbar  — Explore / Tags / Plot Lab (brand titles + actions)
 * - browse  — person / tag / section (toggle + BackLink, no page title in chrome)
 * - sticky  — title detail sticky header
 */
export default function AppShell({
  children,
  className = "app-root",
  testId,
  variant = "topbar",
  title,
  eyebrow,
  leading = null,
  actions = null,
  headerClassName,
  showTitles = true,
}) {
  const { isOwner } = useAuthGate();
  const [navOpen, setNavOpen] = useState(false);

  const headerClass =
    headerClassName ||
    (variant === "browse"
      ? "browse-page-header"
      : variant === "sticky"
        ? "title-detail-sticky-header"
        : "app-topbar");

  const leftClass = variant === "topbar" ? "app-topbar-brand" : "browse-page-header-left";
  const showTopbarTitles = variant === "topbar" && showTitles !== false && title != null;

  return (
    <div className={className} data-testid={testId}>
      <AppNav open={navOpen} onClose={() => setNavOpen(false)} isOwner={isOwner} />
      <header className={headerClass} data-testid="app-shell-header">
        <div className={leftClass}>
          <AppNavToggle open={navOpen} onClick={() => setNavOpen(true)} />
          {leading}
          {showTopbarTitles ? (
            <div className="app-topbar-titles">
              <h1>{title}</h1>
              {eyebrow ? <p className="app-topbar-eyebrow">{eyebrow}</p> : null}
            </div>
          ) : null}
        </div>
        {actions != null ? (
          variant === "topbar" ? <div className="app-topbar-actions">{actions}</div> : actions
        ) : null}
      </header>
      {children}
    </div>
  );
}

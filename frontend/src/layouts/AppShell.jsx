import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import AppNav, { AppNavToggle } from "../components/AppNav";
import { useAuthGate } from "../components/UserMenu";
import { libraryDeleteNoticeFromState } from "../lib/bulkLibraryDelete.js";
import { resolveMemberShell, shellRootClass } from "../lib/memberShell.js";

/**
 * Shared chrome for browse / detail routes.
 * Always provides hamburger AppNav; leaf pages pass BackLink via `leading` or `actions`.
 *
 * Variants:
 * - topbar  — Explore / Tags / Plot Lab (brand titles + actions)
 * - browse  — person / tag / section (toggle + BackLink, no page title in chrome)
 * - sticky  — title detail sticky header
 *
 * Set requireAuth={false} for public pages (e.g. About) so multi-user mode
 * does not redirect anonymous visitors to /login.
 *
 * Youth and guest viewers get distinct shell roots (big posters / tour chrome),
 * not just a thinner adult nav.
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
  requireAuth = true,
}) {
  const { isOwner, role, isYouth, multiUserEnabled } = useAuthGate({ redirect: requireAuth });
  const location = useLocation();
  const [navOpen, setNavOpen] = useState(false);
  const [libraryDeleteNotice, setLibraryDeleteNotice] = useState("");

  useEffect(() => {
    const notice = libraryDeleteNoticeFromState(location.state);
    if (notice) setLibraryDeleteNotice(notice);
  }, [location.key, location.state]);

  const shell = resolveMemberShell({ role, isYouth, multiUserEnabled });
  const rootClass = shellRootClass(shell, className);

  const headerClass =
    headerClassName ||
    (variant === "browse"
      ? "browse-page-header"
      : variant === "sticky"
        ? "title-detail-sticky-header"
        : "app-topbar");

  const leftClass = variant === "topbar" ? "app-topbar-brand" : "browse-page-header-left";
  const showTopbarTitles = variant === "topbar" && showTitles !== false && title != null;
  let shellEyebrow = eyebrow;
  if (!shellEyebrow && shell === "youth") shellEyebrow = "Youth mode";
  if (!shellEyebrow && shell === "guest") shellEyebrow = "Guest tour";

  return (
    <div className={rootClass} data-testid={testId || `${shell}-shell`} data-shell={shell}>
      <AppNav
        open={navOpen}
        onClose={() => setNavOpen(false)}
        isOwner={isOwner}
        isYouth={isYouth}
        role={role}
      />
      <header className={headerClass} data-testid="app-shell-header">
        <div className={leftClass}>
          <AppNavToggle open={navOpen} onClick={() => setNavOpen(true)} />
          {leading}
          {showTopbarTitles ? (
            <div className="app-topbar-titles">
              <h1>{title}</h1>
              {shellEyebrow ? <p className="app-topbar-eyebrow">{shellEyebrow}</p> : null}
            </div>
          ) : null}
        </div>
        {actions != null ? (
          variant === "topbar" ? <div className="app-topbar-actions">{actions}</div> : actions
        ) : null}
      </header>
      {libraryDeleteNotice ? (
        <p className="app-shell-flash status status-secondary" data-testid="library-delete-notice">
          <span>{libraryDeleteNotice}</span>
          <button
            type="button"
            className="ghost"
            data-testid="library-delete-notice-dismiss"
            onClick={() => setLibraryDeleteNotice("")}
          >
            Dismiss
          </button>
        </p>
      ) : null}
      {children}
    </div>
  );
}

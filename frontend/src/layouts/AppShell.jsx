import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import AppNav, { AppNavToggle } from "../components/AppNav";
import PrimaryTopbar from "../components/PrimaryTopbar";
import { useAuthGate } from "../components/UserMenu";
import { libraryDeleteNoticeFromState } from "../lib/bulkLibraryDelete.js";
import { resolveMemberShell, shellRootClass } from "../lib/memberShell.js";
import { applyUiTheme, loadStoredUiTheme } from "../lib/uiPrefs.js";

/**
 * Shared chrome for browse / detail routes.
 *
 * Variants:
 * - topbar  — Explore / Search / My Journey (peer PrimaryTopbar when signed in)
 * - browse  — person / tag / section (toggle + BackLink)
 * - sticky  — title detail sticky header
 *
 * Set requireAuth={false} for public pages (e.g. About) so multi-user mode
 * does not redirect anonymous visitors to /login.
 *
 * Logged-out Help / Privacy / About / Tour use minimal chrome (no hamburger).
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
  chrome,
  showPrimaryNav,
  inboxUnreadCount = 0,
}) {
  const { isOwner, role, isYouth, multiUserEnabled, authenticated } = useAuthGate({
    redirect: requireAuth,
  });
  const location = useLocation();
  const [navOpen, setNavOpen] = useState(false);
  const [libraryDeleteNotice, setLibraryDeleteNotice] = useState("");
  const [uiTheme, setUiTheme] = useState(() => loadStoredUiTheme());

  useEffect(() => {
    const notice = libraryDeleteNoticeFromState(location.state);
    if (notice) setLibraryDeleteNotice(notice);
  }, [location.key, location.state]);

  useEffect(() => {
    applyUiTheme(uiTheme);
  }, [uiTheme]);

  const shell = resolveMemberShell({ role, isYouth, multiUserEnabled });
  const rootClass = shellRootClass(shell, className);

  const forcePublic = chrome === "public" || showPrimaryNav === false;
  const loggedOutPublic = !requireAuth && multiUserEnabled && !authenticated;
  const isPublicChrome = forcePublic || loggedOutPublic;

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
  if (!shellEyebrow && shell === "youth" && !isPublicChrome) shellEyebrow = "Youth mode";
  if (!shellEyebrow && shell === "guest" && !isPublicChrome) shellEyebrow = "Guest tour";

  const usePrimaryToolbar = variant === "topbar" && !isPublicChrome;
  const useLeafHeader = !usePrimaryToolbar && !isPublicChrome;
  const usePublicHeader = isPublicChrome;

  return (
    <div className={rootClass} data-testid={testId || `${shell}-shell`} data-shell={shell}>
      {usePrimaryToolbar ? (
        <>
          <PrimaryTopbar
            showNavToggle
            isOwner={isOwner}
            isYouth={isYouth}
            role={role}
            multiUserEnabled={multiUserEnabled}
            navOpen={navOpen}
            onNavOpenChange={setNavOpen}
            inboxUnreadCount={inboxUnreadCount}
            uiTheme={uiTheme}
            onThemeChange={setUiTheme}
            className={isYouth ? "youth-shell-topbar" : role === "guest" ? "guest-shell-topbar" : ""}
          />
          {title != null || actions != null ? (
            <div className="app-shell-page-bar" data-testid="app-shell-page-bar">
              {title != null ? (
                <div className="app-shell-page-titles">
                  <h1>{title}</h1>
                  {shellEyebrow ? <p className="app-topbar-eyebrow">{shellEyebrow}</p> : null}
                </div>
              ) : (
                <div />
              )}
              {actions != null ? <div className="app-shell-page-actions">{actions}</div> : null}
            </div>
          ) : null}
        </>
      ) : null}

      {useLeafHeader ? (
        <header className={headerClass} data-testid="app-shell-header">
          <div className={leftClass}>
            <AppNav
              open={navOpen}
              onClose={() => setNavOpen(false)}
              isOwner={isOwner}
              isYouth={isYouth}
              role={role}
            />
            <AppNavToggle open={navOpen} onClick={() => setNavOpen(true)} />
            {leading}
            {showTopbarTitles ? (
              <div className="app-topbar-titles">
                <h1>{title}</h1>
                {shellEyebrow ? <p className="app-topbar-eyebrow">{shellEyebrow}</p> : null}
              </div>
            ) : null}
          </div>
          {actions != null ? (variant === "topbar" ? <div className="app-topbar-actions">{actions}</div> : actions) : null}
        </header>
      ) : null}

      {usePublicHeader ? (
        <header className={headerClass} data-testid="app-shell-header">
          <div className={leftClass}>
            {leading}
            {showTopbarTitles ? (
              <div className="app-topbar-titles">
                <h1>{title}</h1>
                {shellEyebrow ? <p className="app-topbar-eyebrow">{shellEyebrow}</p> : null}
              </div>
            ) : null}
          </div>
          {actions != null ? <div className="app-topbar-actions">{actions}</div> : null}
        </header>
      ) : null}

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

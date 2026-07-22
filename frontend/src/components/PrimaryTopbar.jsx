import { Link, useLocation } from "react-router-dom";
import AppNav, { AppNavToggle } from "./AppNav";
import CuratorXBrand from "./CuratorXBrand";
import InboxBadgeButton from "./InboxBadgeButton";
import UserMenu from "./UserMenu";
import { ROUTES } from "../lib/backNav.js";
import {
  buildPrimaryNavItems,
  isPrimaryNavActive,
} from "../lib/primaryNav.js";
import {
  applyUiTheme,
  cycleUiTheme,
  themeControlIcon,
  themePreferenceLabel,
} from "../lib/uiPrefs.js";
import { patchAuthMe } from "../api/client";

/**
 * Shared primary topbar: hamburger (optional) + brand + peer icons + theme + user.
 * Peer order: Search → Chat → Explore → Inbox → Admin → My Journey → Settings.
 */
export default function PrimaryTopbar({
  showNavToggle = true,
  isOwner = false,
  isYouth = false,
  role = "owner",
  multiUserEnabled = false,
  navOpen = false,
  onNavOpenChange,
  brandPulse = "idle",
  chatError = "",
  inboxUnreadCount = 0,
  uiTheme,
  onThemeChange,
  leadingExtra = null,
  className = "",
  showUserMenu = true,
  showThemeToggle = true,
}) {
  const location = useLocation();
  const items = buildPrimaryNavItems({
    role,
    isOwner,
    isYouth,
    multiUserEnabled,
  });

  async function handleThemeClick() {
    if (!onThemeChange) return;
    const next = cycleUiTheme(uiTheme);
    onThemeChange(next);
    applyUiTheme(next);
    try {
      await patchAuthMe({ ui_theme: next });
    } catch {
      // Persist locally even if auth/profile API is unavailable
    }
  }

  return (
    <>
      {showNavToggle ? (
        <AppNav
          open={navOpen}
          onClose={() => onNavOpenChange?.(false)}
          isOwner={isOwner}
          isYouth={isYouth}
          role={role}
        />
      ) : null}
      <header
        className={`app-topbar primary-topbar ${className}`.trim()}
        data-testid="primary-topbar"
      >
        <div className="app-topbar-brand">
          {showNavToggle ? (
            <AppNavToggle
              open={navOpen}
              onClick={() => onNavOpenChange?.(true)}
              testId="app-nav-toggle"
            />
          ) : null}
          {leadingExtra}
          <CuratorXBrand
            pulse={brandPulse}
            chatError={chatError}
            homeTo={ROUTES.chat}
          />
        </div>
        <div className="app-topbar-actions">
          {items.map((item) => {
            const active = isPrimaryNavActive(item, location.pathname);
            const classNames = `app-topbar-icon${active ? " is-active" : ""}`;
            if (item.kind === "inbox") {
              return (
                <InboxBadgeButton
                  key={item.id}
                  unreadCount={inboxUnreadCount}
                  to={item.to}
                  className={classNames}
                  active={active}
                />
              );
            }
            return (
              <Link
                key={item.id}
                to={item.to}
                className={classNames}
                data-testid={item.testId}
                aria-label={item.label}
                aria-current={active ? "page" : undefined}
                data-tooltip={item.label}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  {item.icon}
                </span>
              </Link>
            );
          })}
          {showThemeToggle && uiTheme != null ? (
            <button
              type="button"
              className="app-topbar-icon"
              data-testid="topbar-theme-toggle"
              aria-label={`Theme: ${themePreferenceLabel(uiTheme)}. Click to change.`}
              data-tooltip={themePreferenceLabel(uiTheme)}
              onClick={handleThemeClick}
            >
              <span className="material-symbols-outlined" aria-hidden="true">
                {themeControlIcon(uiTheme)}
              </span>
            </button>
          ) : null}
          {showUserMenu && multiUserEnabled ? <UserMenu /> : null}
        </div>
      </header>
    </>
  );
}

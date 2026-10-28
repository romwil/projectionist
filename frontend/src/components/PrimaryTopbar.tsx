import { Link, useLocation } from "react-router-dom";
import AppNav, { AppNavToggle } from "./AppNav";
import ProjectionistBrand from "./ProjectionistBrand";
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
 * At ≤900px, peers hide into the hamburger so the wordmark never clips.
 */
/** Props for PrimaryTopbar. `any` = API/handler bags until Wave 4 client generics. */
type PrimaryTopbarProps = {
  showNavToggle?: boolean;
  isOwner?: boolean;
  isYouth?: boolean;
  role?: string;
  multiUserEnabled?: boolean;
  seerrEnabled?: boolean;
  authReady?: boolean;
  liveChannelsReady?: boolean;
  navOpen?: any;
  onNavOpenChange?: (...args: any[]) => void;
  brandPulse?: any;
  chatError?: string;
  inboxUnreadCount?: number;
  uiTheme?: any;
  onThemeChange?: (...args: any[]) => void;
  leadingExtra?: any;
  className?: string;
  showUserMenu?: boolean;
  showThemeToggle?: boolean;
  adminBadges?: any;
};

export default function PrimaryTopbar({
  showNavToggle = true,
  isOwner = false,
  isYouth = false,
  role = "owner",
  multiUserEnabled = false,
  seerrEnabled = false,
  authReady = true,
  liveChannelsReady = false,
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
  adminBadges = null,
}: PrimaryTopbarProps) {
  const location = useLocation();
  const items = buildPrimaryNavItems({
    role,
    isOwner,
    isYouth,
    multiUserEnabled,
    authReady,
    liveChannelsReady,
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
          multiUserEnabled={multiUserEnabled}
          seerrEnabled={seerrEnabled}
          authReady={authReady}
          liveChannelsReady={liveChannelsReady}
          adminBadges={adminBadges}
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
          <ProjectionistBrand
            pulse={brandPulse}
            chatError={chatError}
            homeTo={ROUTES.chat}
          />
        </div>
        <div className="app-topbar-actions">
          <div className="app-topbar-peers" data-testid="app-topbar-peers">
            {items.map((item) => {
              const active = isPrimaryNavActive(item, location.pathname);
              const classNames = `app-topbar-icon${active ? " is-active" : ""}`;
              if ((item as any).kind === "inbox") {
                return (
                  <InboxBadgeButton
                    key={(item as any).id}
                    unreadCount={inboxUnreadCount}
                    to={(item as any).to}
                    className={classNames}
                    active={active}
                  />
                );
              }
              return (
                <Link
                  key={(item as any).id}
                  to={(item as any).to}
                  className={classNames}
                  data-testid={(item as any).testId}
                  aria-label={(item as any).label}
                  aria-current={active ? "page" : undefined}
                  data-tooltip={(item as any).label}
                >
                  <span className="material-symbols-outlined" aria-hidden="true">
                    {(item as any).icon}
                  </span>
                </Link>
              );
            })}
          </div>
          <div className="app-topbar-cluster" data-testid="app-topbar-cluster">
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
        </div>
      </header>
    </>
  );
}

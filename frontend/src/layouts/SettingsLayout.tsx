import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { listNotifications } from "../api/client";
import { applyAuthSnapshot, loadAuthSessionUser, loadAuthSnapshot } from "../lib/authGate.js";
import PrimaryTopbar from "../components/PrimaryTopbar";
import { ROUTES } from "../lib/backNav.js";
import { SETTINGS_NAV } from "../lib/settingsNav.js";
import { applyLiveChannelsFeature, initialLiveChannelsReady } from "../lib/liveNavReady.js";
import { applyUiTheme, loadStoredUiTheme } from "../lib/uiPrefs.js";

export { SETTINGS_NAV };

type SettingsNavItem = {
  to: string;
  id: string;
  label: string;
  end?: boolean;
};

type NotificationsPayload = {
  unread_count?: number;
};

export default function SettingsLayout() {
  const navigate = useNavigate();
  const [ready, setReady] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [appNavOpen, setAppNavOpen] = useState(false);
  const [isOwner, setIsOwner] = useState(false);
  const [role, setRole] = useState("owner");
  const [isYouth, setIsYouth] = useState(false);
  const [multiUserEnabled, setMultiUserEnabled] = useState(false);
  const [seerrEnabled, setSeerrEnabled] = useState(false);
  const [liveChannelsReady, setLiveChannelsReady] = useState(initialLiveChannelsReady);
  const [inboxUnreadCount, setInboxUnreadCount] = useState(0);
  const [uiTheme, setUiTheme] = useState(() => loadStoredUiTheme());

  useEffect(() => {
    let cancelled = false;

    async function gate() {
      try {
        const snap = await loadAuthSnapshot();
        if (cancelled) return;
        const view = applyAuthSnapshot(snap, { redirect: true });
        const liveFromFeatures = applyLiveChannelsFeature(snap.features);
        const user = snap.user || (snap.multiUserEnabled ? null : await loadAuthSessionUser());
        if (cancelled) return;
        if (user?.ui_font_size || user?.ui_theme) {
          const { applyUiFontSize, applyUiTheme: applyTheme } = await import("../lib/uiPrefs.js");
          if (user.ui_font_size) applyUiFontSize(user.ui_font_size);
          if (user.ui_theme) applyTheme(user.ui_theme);
        }
        if (view.navigateTo) {
          navigate(view.navigateTo, { replace: true });
          return;
        }
        setIsOwner(view.isOwner);
        setRole(view.role || "member");
        setIsYouth(view.isYouth);
        setMultiUserEnabled(view.multiUserEnabled);
        setSeerrEnabled(view.seerrEnabled);
        if (liveFromFeatures !== null) setLiveChannelsReady(liveFromFeatures);
        setReady(true);
      } catch {
        if (!cancelled) {
          navigate("/login", { replace: true });
        }
      }
    }

    gate();
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  useEffect(() => {
    if (!ready) return undefined;
    let cancelled = false;
    listNotifications({ unread_only: true, limit: 1 })
      .then((data: NotificationsPayload) => {
        if (!cancelled) setInboxUnreadCount(Number(data.unread_count) || 0);
      })
      .catch(() => {
        if (!cancelled) setInboxUnreadCount(0);
      });
    return () => {
      cancelled = true;
    };
  }, [ready]);

  useEffect(() => {
    applyUiTheme(uiTheme);
  }, [uiTheme]);

  if (!ready) {
    return (
      <div className="settings-shell" data-testid="settings-layout-loading">
        <PrimaryTopbar
          showNavToggle
          isOwner={false}
          isYouth={false}
          role="member"
          multiUserEnabled={false}
          seerrEnabled={false}
          authReady={false}
          liveChannelsReady={liveChannelsReady}
          navOpen={appNavOpen}
          onNavOpenChange={setAppNavOpen}
          uiTheme={uiTheme}
          onThemeChange={setUiTheme}
        />
        <div className="settings-shell-loading">
          <p className="status status-secondary">Loading settings…</p>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`settings-shell ${drawerOpen ? "settings-drawer-open" : ""}`}
      data-testid="settings-layout"
    >
      <PrimaryTopbar
        showNavToggle
        isOwner={isOwner}
        isYouth={isYouth}
        role={role}
        multiUserEnabled={multiUserEnabled}
        seerrEnabled={seerrEnabled}
        authReady
        liveChannelsReady={liveChannelsReady}
        navOpen={appNavOpen}
        onNavOpenChange={setAppNavOpen}
        inboxUnreadCount={inboxUnreadCount}
        uiTheme={uiTheme}
        onThemeChange={setUiTheme}
      />
      <header className="shell-app-chrome" data-testid="settings-app-chrome">
        <button
          type="button"
          className="settings-drawer-toggle"
          data-testid="settings-drawer-toggle"
          aria-expanded={drawerOpen}
          aria-controls="settings-nav"
          onClick={() => setDrawerOpen((open) => !open)}
        >
          {drawerOpen ? "Close menu" : "Settings menu"}
        </button>
      </header>
      {drawerOpen ? (
        <button
          type="button"
          className="settings-drawer-backdrop"
          aria-label="Close settings menu"
          onClick={() => setDrawerOpen(false)}
        />
      ) : null}
      <aside className="settings-rail" id="settings-nav" data-testid="settings-rail">
        <div className="settings-rail-brand">
          <p className="eyebrow">Projectionist</p>
          <h1 className="settings-rail-title">Settings</h1>
        </div>
        <nav className="settings-rail-nav" aria-label="Settings sections">
          {(SETTINGS_NAV as SettingsNavItem[]).map((item) => (
            <NavLink
              key={item.id}
              to={item.to}
              end={Boolean(item.end)}
              className={({ isActive }) =>
                `settings-rail-link ${isActive ? "settings-rail-link-active" : ""}`
              }
              data-testid={`settings-nav-${item.id}`}
              onClick={() => setDrawerOpen(false)}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="settings-rail-footer">
          {isOwner ? (
            <Link to="/admin" className="settings-rail-meta-link">
              Admin
            </Link>
          ) : null}
          <Link to={ROUTES.chat} className="settings-rail-meta-link">
            Back to chat
          </Link>
        </div>
      </aside>
      <main className="settings-main">
        <Outlet />
      </main>
      <footer className="app-footer app-footer-full" data-testid="app-footer">
        <Link to="/help" className="app-footer-link">Help</Link>
        <span className="app-footer-sep">·</span>
        <Link to="/privacy" className="app-footer-link">Privacy</Link>
        <span className="app-footer-sep">·</span>
        <Link to="/about" className="app-footer-link">About</Link>
      </footer>
    </div>
  );
}

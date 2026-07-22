import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { getAuthMe, getFeatures, listNotifications } from "../api/client";
import PrimaryTopbar from "../components/PrimaryTopbar";
import { ROUTES } from "../lib/backNav.js";
import { applyUiTheme, loadStoredUiTheme } from "../lib/uiPrefs.js";

export const SETTINGS_NAV = [
  { to: "/settings/profile", id: "profile", label: "Profile" },
  { to: "/settings/voice", id: "voice", label: "Voice" },
  { to: "/settings/taste", id: "taste", label: "Taste" },
  { to: "/settings/notifications", id: "notifications", label: "Notifications" },
  { to: "/settings/watchlist", id: "watchlist", label: "Watchlist" },
  { to: "/settings/lists", id: "lists", label: "Lists" },
];

export default function SettingsLayout() {
  const navigate = useNavigate();
  const [ready, setReady] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [appNavOpen, setAppNavOpen] = useState(false);
  const [isOwner, setIsOwner] = useState(false);
  const [role, setRole] = useState("owner");
  const [isYouth, setIsYouth] = useState(false);
  const [multiUserEnabled, setMultiUserEnabled] = useState(false);
  const [inboxUnreadCount, setInboxUnreadCount] = useState(0);
  const [uiTheme, setUiTheme] = useState(() => loadStoredUiTheme());

  useEffect(() => {
    let cancelled = false;

    async function gate() {
      try {
        const features = await getFeatures();
        const multiUser = Boolean(features?.features?.multi_user_enabled);
        const me = await getAuthMe().catch(() => null);
        if (me?.user?.ui_font_size || me?.user?.ui_theme) {
          const { applyUiFontSize, applyUiTheme: applyTheme } = await import("../lib/uiPrefs.js");
          if (me.user.ui_font_size) applyUiFontSize(me.user.ui_font_size);
          if (me.user.ui_theme) applyTheme(me.user.ui_theme);
        }
        if (!multiUser) {
          if (!cancelled) {
            setIsOwner(true);
            setRole("owner");
            setMultiUserEnabled(false);
            setReady(true);
          }
          return;
        }
        if (cancelled) return;
        if (!me?.user) {
          navigate("/login", { replace: true });
          return;
        }
        setIsOwner(me.user.role === "owner");
        setRole(String(me.user.role || "member"));
        setIsYouth(Boolean(me.user.is_youth));
        setMultiUserEnabled(true);
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
      .then((data) => {
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
      <div className="settings-shell settings-shell-loading" data-testid="settings-layout-loading">
        <p className="status status-secondary">Loading settings…</p>
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
          <p className="eyebrow">CuratorX</p>
          <h1 className="settings-rail-title">Settings</h1>
        </div>
        <nav className="settings-rail-nav" aria-label="Settings sections">
          {SETTINGS_NAV.map((item) => (
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

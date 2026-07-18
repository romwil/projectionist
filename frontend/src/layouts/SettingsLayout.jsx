import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { getAuthMe, getFeatures } from "../api/client";
import AppNav, { AppNavToggle } from "../components/AppNav";

export const SETTINGS_NAV = [
  { to: "/settings/profile", id: "profile", label: "Profile" },
  { to: "/settings/voice", id: "voice", label: "Voice" },
  { to: "/settings/watchlist", id: "watchlist", label: "Watchlist" },
  { to: "/settings/lists", id: "lists", label: "Lists" },
];

export default function SettingsLayout() {
  const navigate = useNavigate();
  const [ready, setReady] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [appNavOpen, setAppNavOpen] = useState(false);
  const [isOwner, setIsOwner] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function gate() {
      try {
        const features = await getFeatures();
        const multiUser = Boolean(features?.features?.multi_user_enabled);
        const me = await getAuthMe().catch(() => null);
        if (me?.user?.ui_font_size || me?.user?.ui_theme) {
          const { applyUiFontSize, applyUiTheme } = await import("../lib/uiPrefs.js");
          if (me.user.ui_font_size) applyUiFontSize(me.user.ui_font_size);
          if (me.user.ui_theme) applyUiTheme(me.user.ui_theme);
        }
        if (!multiUser) {
          if (!cancelled) {
            setIsOwner(true);
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
      <AppNav open={appNavOpen} onClose={() => setAppNavOpen(false)} isOwner={isOwner} />
      <header className="shell-app-chrome" data-testid="settings-app-chrome">
        <AppNavToggle
          open={appNavOpen}
          onClick={() => setAppNavOpen(true)}
          testId="settings-app-nav-toggle"
        />
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
          <Link to="/" className="settings-rail-meta-link">
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

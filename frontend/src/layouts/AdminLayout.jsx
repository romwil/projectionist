import { useEffect, useState } from "react";
import { Link, NavLink, Navigate, Outlet, useNavigate } from "react-router-dom";
import { getAuthMe, getFeatures, listMediaIssues, listNotifications } from "../api/client";
import PrimaryTopbar from "../components/PrimaryTopbar";
import { ROUTES } from "../lib/backNav.js";
import { applyUiTheme, loadStoredUiTheme } from "../lib/uiPrefs.js";

export const ADMIN_NAV = [
  { to: "/admin/overview", id: "overview", label: "Overview" },
  { to: "/admin/connections", id: "connections", label: "Connections" },
  { to: "/admin/libraries", id: "libraries", label: "Libraries" },
  { to: "/admin/sync", id: "sync", label: "Sync" },
  { to: "/admin/tasks", id: "tasks", label: "Scheduled Tasks" },
  { to: "/admin/persona", id: "persona", label: "Persona" },
  { to: "/admin/household", id: "household", label: "Household" },
  { to: "/admin/seerr", id: "seerr", label: "Seerr" },
  { to: "/admin/mail", id: "mail", label: "Mail" },
  { to: "/admin/access", id: "access", label: "Access requests" },
  { to: "/admin/advanced", id: "advanced", label: "Advanced" },
  { to: "/admin/dashboard", id: "dashboard", label: "Dashboard" },
  { to: "/admin/issues", id: "issues", label: "Issues", badge: "openIssues" },
  { to: "/admin/youth", id: "youth", label: "Youth review" },
];

export default function AdminLayout() {
  const navigate = useNavigate();
  const [ready, setReady] = useState(false);
  const [allowed, setAllowed] = useState(false);
  const [wizardMode, setWizardMode] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [appNavOpen, setAppNavOpen] = useState(false);
  const [openIssues, setOpenIssues] = useState(null);
  const [inboxUnreadCount, setInboxUnreadCount] = useState(0);
  const [uiTheme, setUiTheme] = useState(() => loadStoredUiTheme());
  const [multiUserEnabled, setMultiUserEnabled] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function guard() {
      try {
        const features = await getFeatures();
        const multiUser = Boolean(features?.features?.multi_user_enabled);
        if (!cancelled) setMultiUserEnabled(multiUser);
        if (!multiUser) {
          if (!cancelled) {
            setAllowed(true);
            setReady(true);
          }
          return;
        }
        const me = await getAuthMe();
        if (cancelled) return;
        if (!me?.user) {
          navigate("/login", { replace: true });
          return;
        }
        if (me.user.role !== "owner") {
          setAllowed(false);
          setReady(true);
          return;
        }
        setAllowed(true);
        setReady(true);
      } catch {
        if (!cancelled) {
          setAllowed(false);
          setReady(true);
        }
      }
    }

    guard();
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  useEffect(() => {
    if (!allowed) return undefined;
    let cancelled = false;
    listMediaIssues({ status: "open" })
      .then((data) => {
        if (cancelled) return;
        const count = typeof data?.count === "number" ? data.count : (data?.items || []).length;
        setOpenIssues(count);
      })
      .catch(() => {
        if (!cancelled) setOpenIssues(null);
      });
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
  }, [allowed]);

  useEffect(() => {
    applyUiTheme(uiTheme);
  }, [uiTheme]);

  const badgeValue = { openIssues };

  if (!ready) {
    return (
      <div className="admin-shell admin-shell-loading" data-testid="admin-layout-loading">
        <p className="status status-secondary">Loading admin…</p>
      </div>
    );
  }

  if (!allowed) {
    return <Navigate to="/settings" replace />;
  }

  return (
    <div
      className={`admin-shell ${wizardMode ? "admin-shell-wizard" : ""} ${drawerOpen ? "admin-drawer-open" : ""}`}
      data-testid="admin-layout"
    >
      {!wizardMode ? (
        <>
          <PrimaryTopbar
            showNavToggle
            isOwner
            role="owner"
            multiUserEnabled={multiUserEnabled}
            navOpen={appNavOpen}
            onNavOpenChange={setAppNavOpen}
            inboxUnreadCount={inboxUnreadCount}
            uiTheme={uiTheme}
            onThemeChange={setUiTheme}
          />
          <header className="shell-app-chrome" data-testid="admin-app-chrome">
            <button
              type="button"
              className="admin-drawer-toggle"
              data-testid="admin-drawer-toggle"
              aria-expanded={drawerOpen}
              aria-controls="admin-nav"
              onClick={() => setDrawerOpen((open) => !open)}
            >
              {drawerOpen ? "Close menu" : "Admin menu"}
            </button>
          </header>
          {drawerOpen ? (
            <button
              type="button"
              className="admin-drawer-backdrop"
              aria-label="Close admin menu"
              onClick={() => setDrawerOpen(false)}
            />
          ) : null}
          <aside className="admin-rail" id="admin-nav" data-testid="admin-rail">
            <div className="admin-rail-brand">
              <p className="eyebrow">CuratorX</p>
              <h1 className="admin-rail-title">Admin</h1>
            </div>
            <nav className="admin-rail-nav" aria-label="Admin sections">
              {ADMIN_NAV.map((item) => {
                const count = item.badge ? badgeValue[item.badge] : null;
                const showBadge = typeof count === "number" && count > 0;
                return (
                  <NavLink
                    key={item.id}
                    to={item.to}
                    className={({ isActive }) =>
                      `admin-rail-link ${isActive ? "admin-rail-link-active" : ""}`
                    }
                    data-testid={`admin-nav-${item.id}`}
                    onClick={() => setDrawerOpen(false)}
                  >
                    <span>{item.label}</span>
                    {showBadge ? (
                      <span
                        className="admin-rail-badge"
                        data-testid={`admin-nav-badge-${item.id}`}
                        aria-label={`${count} open`}
                      >
                        {count > 99 ? "99+" : count}
                      </span>
                    ) : null}
                  </NavLink>
                );
              })}
            </nav>
            <div className="admin-rail-footer">
              <Link to="/settings" className="admin-rail-meta-link">
                Personal settings
              </Link>
              <Link to={ROUTES.chat} className="admin-rail-meta-link">
                Back to chat
              </Link>
            </div>
          </aside>
        </>
      ) : null}
      <main className="admin-main">
        <Outlet context={{ setWizardMode }} />
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

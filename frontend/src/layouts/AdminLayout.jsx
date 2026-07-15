import { useEffect, useState } from "react";
import { Link, NavLink, Navigate, Outlet, useNavigate } from "react-router-dom";
import { getAuthMe, getFeatures } from "../api/client";

export const ADMIN_NAV = [
  { to: "/admin/overview", id: "overview", label: "Overview" },
  { to: "/admin/connections", id: "connections", label: "Connections" },
  { to: "/admin/libraries", id: "libraries", label: "Libraries" },
  { to: "/admin/sync", id: "sync", label: "Sync" },
  { to: "/admin/persona", id: "persona", label: "Persona" },
  { to: "/admin/household", id: "household", label: "Household" },
  { to: "/admin/seerr", id: "seerr", label: "Seerr" },
  { to: "/admin/advanced", id: "advanced", label: "Advanced" },
  { to: "/admin/dashboard", id: "dashboard", label: "Dashboard" },
];

export default function AdminLayout() {
  const navigate = useNavigate();
  const [ready, setReady] = useState(false);
  const [allowed, setAllowed] = useState(false);
  const [wizardMode, setWizardMode] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function guard() {
      try {
        const features = await getFeatures();
        const multiUser = Boolean(features?.features?.multi_user_enabled);
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
              {ADMIN_NAV.map((item) => (
                <NavLink
                  key={item.id}
                  to={item.to}
                  className={({ isActive }) =>
                    `admin-rail-link ${isActive ? "admin-rail-link-active" : ""}`
                  }
                  data-testid={`admin-nav-${item.id}`}
                  onClick={() => setDrawerOpen(false)}
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
            <div className="admin-rail-footer">
              <Link to="/settings" className="admin-rail-meta-link">
                Personal settings
              </Link>
              <Link to="/privacy" className="admin-rail-meta-link">
                Privacy
              </Link>
              <Link to="/about" className="admin-rail-meta-link">
                About
              </Link>
              <Link to="/" className="admin-rail-meta-link">
                Back to chat
              </Link>
            </div>
          </aside>
        </>
      ) : null}
      <main className="admin-main">
        <Outlet context={{ setWizardMode }} />
      </main>
    </div>
  );
}

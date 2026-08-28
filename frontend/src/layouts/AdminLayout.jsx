import { useEffect, useState } from "react";
import { Link, NavLink, Navigate, Outlet, useNavigate } from "react-router-dom";
import { getAuthMe, getFeatures, listMediaIssues, listNotifications } from "../api/client";
import PrimaryTopbar from "../components/PrimaryTopbar";
import { ADMIN_NAV, adminNavGroups } from "../lib/adminNav.js";
import { ROUTES } from "../lib/backNav.js";
import { applyUiTheme, loadStoredUiTheme } from "../lib/uiPrefs.js";

export { ADMIN_NAV };

export default function AdminLayout() {
  const navigate = useNavigate();
  const [ready, setReady] = useState(false);
  const [allowed, setAllowed] = useState(false);
  const [wizardMode, setWizardMode] = useState(false);
  const [appNavOpen, setAppNavOpen] = useState(false);
  const [openIssues, setOpenIssues] = useState(null);
  const [inboxUnreadCount, setInboxUnreadCount] = useState(0);
  const [uiTheme, setUiTheme] = useState(() => loadStoredUiTheme());
  const [multiUserEnabled, setMultiUserEnabled] = useState(false);
  const [seerrEnabled, setSeerrEnabled] = useState(false);
  const [liveChannelsReady, setLiveChannelsReady] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function guard() {
      try {
        const features = await getFeatures();
        const multiUser = Boolean(features?.features?.multi_user_enabled);
        if (!cancelled) {
          setMultiUserEnabled(multiUser);
          setSeerrEnabled(Boolean(features?.features?.seerr_enabled));
          setLiveChannelsReady(Boolean(features?.features?.live_channels_ready));
        }
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
      className={`admin-shell ${wizardMode ? "admin-shell-wizard" : ""}`}
      data-testid="admin-layout"
    >
      {!wizardMode ? (
        <>
          <PrimaryTopbar
            showNavToggle
            isOwner
            role="owner"
            multiUserEnabled={multiUserEnabled}
            seerrEnabled={seerrEnabled}
            authReady
            liveChannelsReady={liveChannelsReady}
            navOpen={appNavOpen}
            onNavOpenChange={setAppNavOpen}
            inboxUnreadCount={inboxUnreadCount}
            uiTheme={uiTheme}
            onThemeChange={setUiTheme}
            adminBadges={badgeValue}
          />
          <aside className="admin-rail" id="admin-nav" data-testid="admin-rail">
            <div className="admin-rail-brand">
              <p className="eyebrow">Projectionist</p>
              <h1 className="admin-rail-title">Admin</h1>
            </div>
            <nav className="admin-rail-nav" aria-label="Admin sections">
              {adminNavGroups({ multiUserEnabled, seerrEnabled }).map((group, groupIndex) => (
                <section
                  key={group.id}
                  className={`admin-rail-group admin-rail-group-${group.id.replace(/^heading-/, "")}`}
                  data-testid={`admin-nav-group-${group.id}`}
                  aria-labelledby={`admin-rail-${group.id}`}
                >
                  {groupIndex > 0 ? (
                    <hr className="admin-rail-group-rule" data-testid={`admin-nav-rule-${group.id}`} />
                  ) : null}
                  <div className="admin-rail-group-band">
                    <p
                      id={`admin-rail-${group.id}`}
                      className="admin-rail-heading"
                      data-testid={`admin-nav-${group.id}`}
                    >
                      {group.label}
                    </p>
                    <div className="admin-rail-group-links">
                      {group.links.map((item) => {
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
                    </div>
                  </div>
                  {group.subtitle ? (
                    <p className="admin-rail-group-note" data-testid={`admin-nav-${group.id}-note`}>
                      {group.subtitle}
                    </p>
                  ) : null}
                </section>
              ))}
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

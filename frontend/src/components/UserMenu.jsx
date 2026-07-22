import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getAuthMe, getFeatures, logout } from "../api/client";
import UserAvatar from "./UserAvatar";
import { useAnchoredPopover } from "../hooks/useAnchoredPopover";

export default function UserMenu() {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const { open, setOpen, rootRef: menuRef } = useAnchoredPopover();

  useEffect(() => {
    getAuthMe()
      .then((payload) => setUser(payload?.user || null))
      .catch(() => setUser(null));
  }, []);

  async function handleLogout() {
    try {
      await logout();
    } catch {
      // Still redirect after clearing cookie attempt.
    }
    navigate("/login", { replace: true });
  }

  if (!user) return null;

  const isOwner = user.role === "owner";

  return (
    <div className="user-menu" ref={menuRef} data-testid="user-menu">
      <button
        type="button"
        className="user-menu-trigger"
        data-testid="user-menu-trigger"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <UserAvatar user={user} />
        <span className="user-menu-name">{user.display_name}</span>
      </button>
      {open ? (
        <div className="user-menu-panel" data-testid="user-menu-panel">
          <p className="user-menu-meta">
            {user.display_name}
            <span>{user.role}</span>
          </p>
          {isOwner ? (
            <Link to="/admin" className="user-menu-link" onClick={() => setOpen(false)}>
              Admin
            </Link>
          ) : null}
          <Link to="/settings" className="user-menu-link" onClick={() => setOpen(false)}>
            Settings
          </Link>
          <Link to="/help" className="user-menu-link" data-testid="user-menu-help" onClick={() => setOpen(false)}>
            Help
          </Link>
          <Link to="/about" className="user-menu-link" onClick={() => setOpen(false)}>
            About
          </Link>
          <button type="button" className="user-menu-link" data-testid="logout-button" onClick={handleLogout}>
            Sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}

/**
 * Auth gate for browse shells.
 * @param {{ redirect?: boolean }} [options] When redirect is false (public pages
 *   like About), never send the user to /login — still resolve isOwner when possible.
 */
export function useAuthGate({ redirect = true } = {}) {
  const navigate = useNavigate();
  const [authReady, setAuthReady] = useState(false);
  const [multiUserEnabled, setMultiUserEnabled] = useState(false);
  const [isOwner, setIsOwner] = useState(true);
  const [role, setRole] = useState("owner");
  const [isYouth, setIsYouth] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function checkAuth() {
      let enabled = false;
      try {
        const features = await getFeatures();
        enabled = Boolean(features?.features?.multi_user_enabled);
        if (cancelled) return;
        setMultiUserEnabled(enabled);
        if (!enabled) {
          setIsOwner(true);
          setRole("owner");
          setIsYouth(false);
          setAuthReady(true);
          try {
            const me = await getAuthMe();
            if (!cancelled && (me?.user?.ui_font_size || me?.user?.ui_theme)) {
              const { applyUiFontSize, applyUiTheme } = await import("../lib/uiPrefs.js");
              if (me.user.ui_font_size) applyUiFontSize(me.user.ui_font_size);
              if (me.user.ui_theme) applyUiTheme(me.user.ui_theme);
            }
          } catch {
            // ignore
          }
          return;
        }
        const me = await getAuthMe();
        if (cancelled) return;
        if (!me) {
          if (redirect) {
            navigate("/login", { replace: true });
            return;
          }
          setIsOwner(false);
          setRole("guest");
          setIsYouth(false);
          setAuthReady(true);
          return;
        }
        if (me.user?.ui_font_size || me.user?.ui_theme) {
          const { applyUiFontSize, applyUiTheme } = await import("../lib/uiPrefs.js");
          if (me.user.ui_font_size) applyUiFontSize(me.user.ui_font_size);
          if (me.user.ui_theme) applyUiTheme(me.user.ui_theme);
        }
        const nextRole = String(me.user?.role || "guest").toLowerCase();
        setRole(nextRole === "owner" || nextRole === "member" || nextRole === "guest" ? nextRole : "guest");
        setIsOwner(nextRole === "owner");
        setIsYouth(Boolean(me.user?.is_youth));
        setAuthReady(true);
      } catch {
        if (cancelled) return;
        // Multi-user must not failure-open into the app on auth/network errors.
        if (enabled) {
          if (redirect) {
            navigate("/login", { replace: true });
            return;
          }
          setIsOwner(false);
          setRole("guest");
          setIsYouth(false);
          setAuthReady(true);
          return;
        }
        setIsOwner(true);
        setRole("owner");
        setIsYouth(false);
        setAuthReady(true);
      }
    }

    checkAuth();
    return () => {
      cancelled = true;
    };
  }, [navigate, redirect]);

  return { authReady, multiUserEnabled, isOwner, role, isYouth };
}

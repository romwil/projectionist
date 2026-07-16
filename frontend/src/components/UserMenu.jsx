import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getAuthMe, getFeatures, logout } from "../api/client";

function initials(name) {
  const parts = String(name || "U")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!parts.length) return "U";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] || ""}${parts[1][0] || ""}`.toUpperCase();
}

export default function UserMenu() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [user, setUser] = useState(null);
  const menuRef = useRef(null);

  useEffect(() => {
    getAuthMe()
      .then((payload) => setUser(payload?.user || null))
      .catch(() => setUser(null));
  }, []);

  useEffect(() => {
    function handleClick(event) {
      if (!menuRef.current?.contains(event.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
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
        {user.avatar_url ? (
          <img src={user.avatar_url} alt="" className="user-menu-avatar" />
        ) : (
          <span className="user-menu-avatar user-menu-avatar-fallback">{initials(user.display_name)}</span>
        )}
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

export function useAuthGate() {
  const navigate = useNavigate();
  const [authReady, setAuthReady] = useState(false);
  const [multiUserEnabled, setMultiUserEnabled] = useState(false);
  const [isOwner, setIsOwner] = useState(true);

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
          setAuthReady(true);
          try {
            const me = await getAuthMe();
            if (!cancelled && me?.user?.ui_font_size) {
              const { applyUiFontSize } = await import("../lib/uiPrefs.js");
              applyUiFontSize(me.user.ui_font_size);
            }
          } catch {
            // ignore
          }
          return;
        }
        const me = await getAuthMe();
        if (cancelled) return;
        if (!me) {
          navigate("/login", { replace: true });
          return;
        }
        if (me.user?.ui_font_size) {
          const { applyUiFontSize } = await import("../lib/uiPrefs.js");
          applyUiFontSize(me.user.ui_font_size);
        }
        setIsOwner(me.user?.role === "owner");
        setAuthReady(true);
      } catch {
        if (cancelled) return;
        // Multi-user must not failure-open into the app on auth/network errors.
        if (enabled) {
          navigate("/login", { replace: true });
          return;
        }
        setIsOwner(true);
        setAuthReady(true);
      }
    }

    checkAuth();
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  return { authReady, multiUserEnabled, isOwner };
}

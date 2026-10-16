import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { logout } from "../api/client";
import {
  applyAuthSnapshot,
  clearAuthSnapshot,
  loadAuthSessionUser,
  loadAuthSnapshot,
  peekAuthSnapshot,
} from "../lib/authGate.js";
import { applyLiveChannelsFeature, initialLiveChannelsReady } from "../lib/liveNavReady.js";
import UserAvatar from "./UserAvatar";
import { useAnchoredPopover } from "../hooks/useAnchoredPopover";

export default function UserMenu() {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const { open, setOpen, rootRef: menuRef } = useAnchoredPopover();

  useEffect(() => {
    let cancelled = false;
    loadAuthSnapshot()
      .then(async (snap) => {
        const next = snap.user || (snap.multiUserEnabled ? null : await loadAuthSessionUser());
        if (!cancelled) setUser(next);
      })
      .catch(() => {
        if (!cancelled) setUser(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleLogout() {
    try {
      await logout();
    } catch {
      // Still redirect after clearing cookie attempt.
    }
    clearAuthSnapshot();
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
  const seeded = peekAuthSnapshot();
  const seededView = seeded ? applyAuthSnapshot(seeded, { redirect }) : null;
  const [authReady, setAuthReady] = useState(Boolean(seededView?.authReady));
  const [multiUserEnabled, setMultiUserEnabled] = useState(Boolean(seededView?.multiUserEnabled));
  const [isOwner, setIsOwner] = useState(seededView ? seededView.isOwner : false);
  const [role, setRole] = useState(seededView?.role || "member");
  const [isYouth, setIsYouth] = useState(Boolean(seededView?.isYouth));
  const [authenticated, setAuthenticated] = useState(Boolean(seededView?.authenticated));
  const [liveChannelsReady, setLiveChannelsReady] = useState(initialLiveChannelsReady);
  const [seerrEnabled, setSeerrEnabled] = useState(Boolean(seededView?.seerrEnabled));

  useEffect(() => {
    let cancelled = false;

    loadAuthSnapshot().then(async (snap) => {
      if (cancelled) return;
      applyLiveChannelsFeature(snap.features, setLiveChannelsReady);
      const view = applyAuthSnapshot(snap, { redirect });
      if (view.navigateTo) {
        navigate(view.navigateTo, { replace: true });
        return;
      }
      setMultiUserEnabled(view.multiUserEnabled);
      setSeerrEnabled(view.seerrEnabled);
      setIsOwner(view.isOwner);
      setRole(view.role);
      setIsYouth(view.isYouth);
      setAuthenticated(view.authenticated);
      setAuthReady(true);
      const user = snap.user || (snap.multiUserEnabled ? null : await loadAuthSessionUser());
      if (cancelled || !user || !(user.ui_font_size || user.ui_theme)) return;
      const { applyUiFontSize, applyUiTheme } = await import("../lib/uiPrefs.js");
      if (cancelled) return;
      if (user.ui_font_size) applyUiFontSize(user.ui_font_size);
      if (user.ui_theme) applyUiTheme(user.ui_theme);
    });

    return () => {
      cancelled = true;
    };
  }, [navigate, redirect]);

  return {
    authReady,
    multiUserEnabled,
    isOwner,
    role,
    isYouth,
    authenticated,
    liveChannelsReady,
    seerrEnabled,
  };
}

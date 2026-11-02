import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuthGate } from "./UserMenu";
import { useInboxUnreadCount } from "../hooks/useInboxUnreadCount";
import {
  buildPrimaryBottomNavItems,
  isPrimaryNavActive,
  shouldHidePrimaryBottomNav,
} from "../lib/primaryNav.js";
import { isIosSafariUserAgent } from "../lib/theaterPlayer.js";

const COMPOSER_SELECTOR = "[data-testid='composer-input']";

/**
 * UX-014: a real primary nav for phones/iPads — the same role-correct
 * peers as the topbar/drawer (capped at 5), with the Inbox badge wired to
 * `inboxUnreadCount`. Hidden over the player and while the iOS keyboard
 * would otherwise cover it. Desktop/tablet-landscape hide it via CSS
 * (`.primary-bottom-nav` media query) — this component only handles the
 * route/composer-focus cases CSS can't.
 */
export default function PrimaryBottomNav() {
  const location = useLocation();
  const { role, isOwner, isYouth, multiUserEnabled, authReady, liveChannelsReady, authenticated } =
    useAuthGate({ redirect: false });
  const unreadCount = useInboxUnreadCount({ enabled: authenticated });
  const [composerFocused, setComposerFocused] = useState(false);

  useEffect(() => {
    function syncFocus() {
      const active = document.activeElement;
      setComposerFocused(Boolean(active && active.matches?.(COMPOSER_SELECTOR)));
    }
    syncFocus();
    document.addEventListener("focusin", syncFocus);
    document.addEventListener("focusout", syncFocus);
    return () => {
      document.removeEventListener("focusin", syncFocus);
      document.removeEventListener("focusout", syncFocus);
    };
  }, []);

  if (
    !authReady ||
    !authenticated ||
    shouldHidePrimaryBottomNav({
      pathname: location.pathname,
      composerFocused,
      isIos: isIosSafariUserAgent(typeof navigator !== "undefined" ? navigator.userAgent : ""),
    })
  ) {
    return null;
  }

  const items = buildPrimaryBottomNavItems({
    role,
    isOwner,
    isYouth,
    multiUserEnabled,
    authReady,
    liveChannelsReady,
  });

  return (
    <nav className="primary-bottom-nav" data-testid="primary-bottom-nav" aria-label="Primary">
      {items.map((item) => {
        const active = isPrimaryNavActive(item, location.pathname);
        const showBadge = item.kind === "inbox" && unreadCount > 0;
        return (
          <Link
            key={item.id}
            to={item.to}
            className={`primary-bottom-nav-item${active ? " is-active" : ""}`}
            data-testid={`bottom-nav-${item.id}`}
            aria-current={active ? "page" : undefined}
          >
            <span className="primary-bottom-nav-icon-wrap">
              <span className="material-symbols-outlined primary-bottom-nav-icon" aria-hidden="true">
                {item.icon}
              </span>
              {showBadge ? (
                <span className="primary-bottom-nav-badge" data-testid="bottom-nav-inbox-badge">
                  {unreadCount > 9 ? "9+" : unreadCount}
                </span>
              ) : null}
            </span>
            <span className="primary-bottom-nav-label">{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

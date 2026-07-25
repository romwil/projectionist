import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import {
  listNotifications,
  markNotificationsSeen,
} from "../api/client";
import RecommendationsInbox from "../components/RecommendationsInbox";
import { useAuthGate } from "../components/UserMenu";
import AppShell from "../layouts/AppShell";
import { ROUTES } from "../lib/backNav.js";
import { guestDeepLinkBlocked } from "../lib/memberShell.js";

/**
 * Top-level Inbox — household notifications live here (not on Chat).
 */
export default function InboxPage() {
  const { authReady, role, multiUserEnabled } = useAuthGate();
  const [state, setState] = useState({ loading: true, items: [], error: "", unread: 0 });

  function reload() {
    setState((prev) => ({ ...prev, loading: true, error: "" }));
    listNotifications({ unread_only: false, limit: 50 })
      .then((data) => {
        setState({
          loading: false,
          items: data.items || [],
          error: "",
          unread: Number(data.unread_count) || 0,
        });
      })
      .catch((err) => {
        setState({
          loading: false,
          items: [],
          error: err.message || "Could not load inbox.",
          unread: 0,
        });
      });
  }

  useEffect(() => {
    if (!authReady || guestDeepLinkBlocked({ role, multiUserEnabled, authReady })) return;
    reload();
  }, [authReady, role, multiUserEnabled]);

  async function handleDismiss(rec) {
    if (!rec?.id) return;
    setState((prev) => ({
      ...prev,
      items: prev.items.filter((item) => item.id !== rec.id),
      unread: Math.max(0, prev.unread - 1),
    }));
    try {
      await markNotificationsSeen({ ids: [rec.id] });
    } catch {
      reload();
    }
  }

  async function handleDismissAll(items) {
    setState((prev) => ({ ...prev, items: [], unread: 0 }));
    try {
      if (items?.length) {
        await markNotificationsSeen({ ids: items.map((item) => item.id) });
      } else {
        await markNotificationsSeen({ all_unread: true });
      }
    } catch {
      reload();
    }
  }

  if (!authReady) {
    return (
      <div className="app-root app-loading" data-testid="inbox-auth-loading">
        <p className="login-lede">Loading…</p>
      </div>
    );
  }

  if (guestDeepLinkBlocked({ role, multiUserEnabled, authReady: true })) {
    return <Navigate to={ROUTES.explore} replace />;
  }

  return (
    <AppShell
      className="app-root inbox-page"
      testId="inbox-page"
      title="Inbox"
      eyebrow="Recommendations & notifications"
      inboxUnreadCount={state.unread}
    >
      <main className="explore-main inbox-main">
        {state.loading ? <p className="status status-secondary">Loading inbox…</p> : null}
        {state.error ? <p className="status status-error">{state.error}</p> : null}
        {!state.loading && !state.error && !state.items.length ? (
          <section className="explore-section" data-testid="inbox-empty">
            <p className="explore-empty status status-secondary">
              Nothing waiting — when someone recommends a title or a request lands, it shows up here.
              Head back to{" "}
              <a href={ROUTES.chat}>Chat</a> or{" "}
              <a href={ROUTES.explore}>Explore</a> anytime.
            </p>
          </section>
        ) : null}
        {!state.loading && state.items.length ? (
          <RecommendationsInbox
            items={state.items}
            onDismiss={handleDismiss}
            onDismissAll={handleDismissAll}
          />
        ) : null}
      </main>
    </AppShell>
  );
}

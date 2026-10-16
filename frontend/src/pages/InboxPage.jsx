import { useCallback, useEffect, useRef, useState } from "react";
import { Navigate } from "react-router-dom";
import {
  listNotifications,
  markNotificationsSeen,
} from "../api/client";
import ChamberEmpty from "../components/ChamberEmpty";
import RecommendationsInbox from "../components/RecommendationsInbox";
import { useAuthGate } from "../components/UserMenu";
import AppShell from "../layouts/AppShell";
import { ROUTES } from "../lib/backNav.js";
import { guestDeepLinkBlocked } from "../lib/memberShell.js";
import {
  INBOX_FIRST_PAINT_PARAMS,
  inboxFollowUpParams,
} from "../lib/recommendationInbox.js";

/**
 * Top-level Inbox — household notifications live here (not on Chat).
 *
 * The shell paints immediately. The first unread page loads in parallel with
 * auth (the session cookie rides on the request). Older unread rows follow
 * after those cards are on screen.
 */
export default function InboxPage() {
  const { authReady, role, multiUserEnabled } = useAuthGate();
  const [state, setState] = useState({ loading: true, items: [], error: "", unread: 0 });
  const loadGen = useRef(0);

  const loadInbox = useCallback(() => {
    const gen = ++loadGen.current;
    const cancelled = () => gen !== loadGen.current;
    // Unread-only: dismiss marks seen_at; refetching history made clear-all look temporary.
    listNotifications(INBOX_FIRST_PAINT_PARAMS)
      .then(async (data) => {
        if (cancelled()) return;
        const firstItems = data.items || [];
        const unread = Number(data.unread_count) || 0;
        setState({
          loading: false,
          items: firstItems,
          error: "",
          unread,
        });
        const restParams = inboxFollowUpParams(firstItems.length, unread);
        if (!restParams) return;
        const rest = await listNotifications(restParams);
        if (cancelled()) return;
        setState((prev) => {
          if (!prev.items.length) return prev;
          const visible = new Set(prev.items.map((item) => item.id));
          const kept = firstItems.filter((item) => visible.has(item.id));
          const seen = new Set(kept.map((item) => item.id));
          const older = (rest.items || []).filter((item) => !seen.has(item.id));
          return {
            ...prev,
            items: [...kept, ...older],
            unread: Number(rest.unread_count) || prev.unread,
          };
        });
      })
      .catch((err) => {
        if (cancelled()) return;
        if (err?.status === 401) {
          setState((prev) => ({ ...prev, loading: false, error: "" }));
          return;
        }
        setState({
          loading: false,
          items: [],
          error: err.message || "Could not load inbox.",
          unread: 0,
        });
      });
  }, []);

  useEffect(() => {
    loadInbox();
    // Do not wait for authReady. A second effect run after getFeatures/getAuthMe
    // used to start the list only after that chain, and again inside AppShell.
    return () => {
      loadGen.current += 1;
    };
  }, [loadInbox]);

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
      setState((prev) => ({ ...prev, loading: true, error: "" }));
      loadInbox();
    }
  }

  async function handleDismissAll() {
    loadGen.current += 1;
    setState((prev) => ({ ...prev, items: [], unread: 0 }));
    try {
      // Always clear every unread row — not only the currently rendered/deduped ids.
      await markNotificationsSeen({ all_unread: true });
    } catch {
      setState((prev) => ({ ...prev, loading: true, error: "" }));
      loadInbox();
    }
  }

  if (authReady && guestDeepLinkBlocked({ role, multiUserEnabled, authReady: true })) {
    return <Navigate to={ROUTES.explore} replace />;
  }

  return (
    <AppShell
      className="app-root inbox-page"
      testId="inbox-page"
      title="Inbox"
      inboxUnreadCount={state.unread}
      blockUntilAuth={false}
    >
      <main className="explore-main inbox-main">
        {state.loading && !state.items.length ? (
          <p className="status status-secondary">Loading inbox…</p>
        ) : null}
        {state.error ? <p className="status status-error">{state.error}</p> : null}
        {!state.loading && !state.error && !state.items.length ? (
          <section className="explore-section" data-testid="inbox-empty">
            <ChamberEmpty
              title="Nothing waiting"
              body="When someone recommends a title or a request lands, it shows up here."
              ctaLabel="Back to Explore"
              ctaTo={ROUTES.explore}
              testId="inbox-empty-state"
            />
          </section>
        ) : null}
        {state.items.length ? (
          <RecommendationsInbox
            items={state.items}
            role={role}
            onDismiss={handleDismiss}
            onDismissAll={handleDismissAll}
          />
        ) : null}
      </main>
    </AppShell>
  );
}

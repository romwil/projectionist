import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { getFeatures, getGuestTour } from "../api/client";
import AppShell from "../layouts/AppShell";
import { ROUTES } from "../lib/backNav.js";

/**
 * Guest tour shell — "what's great here" over published collections.
 * Public chrome (no hamburger) when the feature flag is on.
 */
export default function GuestTourPage() {
  const [flag, setFlag] = useState({ loading: true, enabled: false });
  const [state, setState] = useState({ loading: true, items: [], error: "", title: "", lede: "" });

  useEffect(() => {
    let cancelled = false;
    getFeatures()
      .then((data) => {
        if (cancelled) return;
        setFlag({
          loading: false,
          enabled: Boolean(data?.features?.guest_tour_enabled),
        });
      })
      .catch(() => {
        if (!cancelled) setFlag({ loading: false, enabled: false });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (flag.loading || !flag.enabled) return undefined;
    let cancelled = false;
    getGuestTour()
      .then((data) => {
        if (cancelled) return;
        setState({
          loading: false,
          items: data?.items || [],
          error: "",
          title: data?.title || "What's great here",
          lede: data?.lede || "",
        });
      })
      .catch((error) => {
        if (!cancelled) {
          setState({
            loading: false,
            items: [],
            error: error.message || "Could not load the tour.",
            title: "What's great here",
            lede: "",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [flag.loading, flag.enabled]);

  if (!flag.loading && !flag.enabled) {
    return <Navigate to="/login" replace />;
  }

  return (
    <AppShell
      className="app-root guest-tour-page"
      testId="guest-tour-page"
      variant="topbar"
      title={state.title || "What's great here"}
      eyebrow="Guest tour"
      requireAuth={false}
      chrome="public"
      actions={<Link to="/login" className="app-topbar-link">Sign in</Link>}
    >
      <main className="guest-tour-main">
        {flag.loading || state.loading ? (
          <p className="status status-secondary">Loading the tour…</p>
        ) : null}
        {state.lede ? <p className="guest-tour-lede">{state.lede}</p> : null}
        {state.error ? <p className="error">{state.error}</p> : null}
        {!flag.loading && !state.loading && !state.error ? (
          state.items.length ? (
            <div className="guest-tour-grid" data-testid="guest-tour-grid">
              {state.items.map((list) => (
                <Link
                  key={list.id}
                  to={`/collections/${list.id}`}
                  className="guest-tour-card"
                  data-testid={`guest-tour-card-${list.id}`}
                >
                  <p className="guest-tour-card-kind">
                    {list.list_kind === "course" ? "Course" : "Collection"}
                  </p>
                  <h2>{list.name}</h2>
                  <p>{list.description || `${list.item_count || 0} titles your host wants you to see.`}</p>
                </Link>
              ))}
            </div>
          ) : (
            <p className="status status-secondary" data-testid="guest-tour-empty">
              No published collections yet — ask your host what they love from this library.
            </p>
          )
        ) : null}
        <p className="guest-tour-cta">
          <Link to={ROUTES.explore} className="primary" data-testid="guest-tour-browse">
            Browse the shelves
          </Link>
          <Link to={ROUTES.chat} className="ghost" data-testid="guest-tour-ask">
            Ask the curator
          </Link>
        </p>
      </main>
    </AppShell>
  );
}

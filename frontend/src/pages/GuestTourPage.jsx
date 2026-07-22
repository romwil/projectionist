import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getGuestTour } from "../api/client";
import AppShell from "../layouts/AppShell";

/**
 * Guest tour shell — "what's great here" over published collections.
 */
export default function GuestTourPage() {
  const [state, setState] = useState({ loading: true, items: [], error: "", title: "", lede: "" });

  useEffect(() => {
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
  }, []);

  return (
    <AppShell
      className="app-root guest-tour-page"
      testId="guest-tour-page"
      variant="topbar"
      title={state.title}
      eyebrow="Guest tour"
    >
      <main className="guest-tour-main">
        {state.lede ? <p className="guest-tour-lede">{state.lede}</p> : null}
        {state.loading ? <p className="status status-secondary">Loading the tour…</p> : null}
        {state.error ? <p className="error">{state.error}</p> : null}
        {!state.loading && !state.error ? (
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
          <Link to="/explore" className="primary" data-testid="guest-tour-browse">
            Browse the shelves
          </Link>
          <Link to="/" className="ghost" data-testid="guest-tour-ask">
            Ask the curator
          </Link>
        </p>
      </main>
    </AppShell>
  );
}

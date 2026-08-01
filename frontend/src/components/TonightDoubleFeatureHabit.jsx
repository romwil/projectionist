import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getTonightDoubleFeature } from "../api/client";
import DoubleFeatureCard from "./DoubleFeatureCard";
import { ROUTES } from "../lib/backNav.js";

/**
 * Explore habit: Companion/Concierge-style owned double feature with a why.
 */
export default function TonightDoubleFeatureHabit() {
  const [state, setState] = useState({ loading: true, payload: null, error: "" });

  useEffect(() => {
    let cancelled = false;
    getTonightDoubleFeature()
      .then((payload) => {
        if (!cancelled) setState({ loading: false, payload, error: "" });
      })
      .catch((err) => {
        if (!cancelled) {
          setState({
            loading: false,
            payload: null,
            error: err.message || "Could not pair a double feature.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const payload = state.payload;
  const ready = Boolean(payload?.title_a && payload?.title_b);

  return (
    <section className="tonight-double-feature" data-testid="tonight-double-feature">
      <header className="explore-section-header">
        <div>
          <p className="eyebrow">Tonight</p>
          <h2>Tonight’s double feature</h2>
          <p className="explore-section-subtitle">
            Two owned titles paired with a why — ask Companion or Concierge to reshuffle in chat.
          </p>
        </div>
        <Link className="ghost" to={ROUTES.chat} data-testid="tonight-double-feature-chat">
          Ask for another pair
        </Link>
      </header>
      {state.loading ? <p className="status status-secondary">Pairing two titles…</p> : null}
      {state.error ? <p className="error">{state.error}</p> : null}
      {!state.loading && !ready ? (
        <p className="status status-secondary" data-testid="tonight-double-feature-empty">
          {payload?.note || "Need a couple of owned movies before we can pair a double feature."}
        </p>
      ) : null}
      {ready ? (
        <DoubleFeatureCard
          titleA={payload.title_a}
          titleB={payload.title_b}
          bridgeText={payload.bridge_text || payload.lede || ""}
          combinedRuntime={payload.combined_runtime || 0}
        />
      ) : null}
    </section>
  );
}

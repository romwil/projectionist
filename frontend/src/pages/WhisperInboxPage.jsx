import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listWhispers, markWhispersSeen } from "../api/client";
import ChamberEmpty from "../components/ChamberEmpty";
import { useAuthGate } from "../components/UserMenu";
import AppShell from "../layouts/AppShell";
import { ROUTES } from "../lib/backNav.js";
import { titleDetailPath } from "../lib/titleLinks.js";
import {
  isForbiddenWhisperCopy,
  whisperInboxHeadline,
  whisperMemberName,
  whisperWhy,
  whyWordCount,
} from "../lib/whisperInbox.js";

function WhisperCard({ item, memberName, onDismiss }) {
  const why = whisperWhy(item);
  const safeWhy = isForbiddenWhisperCopy(why) ? "" : why;
  const yearBit = item?.year ? ` (${item.year})` : "";
  const href = titleDetailPath(item);
  const title = String(item?.title || "A title").trim() || "A title";

  return (
    <article className="whisper-card" data-testid="whisper-card">
      <p className="whisper-card-eyebrow">{whisperMemberName(item, memberName)}</p>
      <h2 className="whisper-card-title">
        {href ? (
          <Link to={href} className="whisper-card-title-link" data-testid="whisper-card-title">
            {title}
            {yearBit}
          </Link>
        ) : (
          <span data-testid="whisper-card-title">
            {title}
            {yearBit}
          </span>
        )}
      </h2>
      {safeWhy && whyWordCount(safeWhy) > 0 ? (
        <p className="whisper-card-why" data-testid="whisper-card-why">
          {safeWhy}
        </p>
      ) : null}
      <button
        type="button"
        className="ghost whisper-card-dismiss"
        data-testid="whisper-card-dismiss"
        onClick={() => onDismiss?.(item)}
      >
        Heard
      </button>
    </article>
  );
}

export default function WhisperInboxPage() {
  const { authReady } = useAuthGate();
  const [state, setState] = useState({
    loading: true,
    items: [],
    error: "",
    memberName: "",
    unread: 0,
  });

  function reload() {
    setState((prev) => ({ ...prev, loading: true, error: "" }));
    listWhispers({ unread_only: true, limit: 20 })
      .then((data) => {
        setState({
          loading: false,
          items: data.items || [],
          error: "",
          memberName: String(data.member_name || "").trim(),
          unread: Number(data.unread_count) || 0,
        });
      })
      .catch((err) => {
        setState({
          loading: false,
          items: [],
          error: err.message || "Could not load whispers.",
          memberName: "",
          unread: 0,
        });
      });
  }

  useEffect(() => {
    if (!authReady) return;
    reload();
  }, [authReady]);

  async function handleDismiss(item) {
    if (!item?.id) return;
    setState((prev) => ({
      ...prev,
      items: prev.items.filter((row) => row.id !== item.id),
      unread: Math.max(0, prev.unread - 1),
    }));
    try {
      await markWhispersSeen({ ids: [item.id] });
    } catch {
      reload();
    }
  }

  async function handleDismissAll() {
    setState((prev) => ({ ...prev, items: [], unread: 0 }));
    try {
      await markWhispersSeen({ all_unread: true });
    } catch {
      reload();
    }
  }

  if (!authReady) {
    return (
      <div className="app-root app-loading" data-testid="whisper-auth-loading">
        <p className="login-lede">Loading…</p>
      </div>
    );
  }

  const headline = whisperInboxHeadline({
    memberName: state.memberName,
    count: state.items.length,
  });

  return (
    <AppShell
      className="app-root whisper-inbox-page"
      testId="whisper-inbox-page"
      title={headline}
    >
      <main className="explore-main whisper-inbox-main">
        {state.loading ? <p className="status status-secondary">Loading whispers…</p> : null}
        {state.error ? <p className="status status-error">{state.error}</p> : null}
        {!state.loading && !state.error && !state.items.length ? (
          <section className="explore-section" data-testid="whisper-inbox-empty">
            <ChamberEmpty
              title={state.memberName ? `Nothing whispered for ${state.memberName}` : "Nothing whispered"}
              body="When the curator has a quiet pick for you, the twelve-word why lands here — not a download ping."
              ctaLabel="Back to chat"
              ctaTo={ROUTES.chat}
              testId="whisper-inbox-empty-state"
            />
          </section>
        ) : null}
        {!state.loading && state.items.length ? (
          <section className="whisper-inbox-list" data-testid="whisper-inbox-list">
            {state.items.length > 1 ? (
              <button
                type="button"
                className="ghost whisper-inbox-clear"
                data-testid="whisper-inbox-clear"
                onClick={handleDismissAll}
              >
                Heard all
              </button>
            ) : null}
            {state.items.map((item) => (
              <WhisperCard
                key={item.id}
                item={item}
                memberName={state.memberName}
                onDismiss={handleDismiss}
              />
            ))}
          </section>
        ) : null}
      </main>
    </AppShell>
  );
}

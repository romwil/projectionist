import { useEffect, useState } from "react";
import { createRecommendations, listHouseholdPeers } from "../api/client";
import {
  WATCH_PARTY_NOTE_CHIPS,
  defaultWatchPartyNote,
  normalizeRecommendIntent,
  recommendModalCopy,
} from "../lib/householdSocial.js";
import { useBulkActionProgress } from "./BulkActionProgress";

export default function RecommendModal({ item, open, onClose, onSent, defaultIntent = "recommend" }) {
  const { start, update, finish } = useBulkActionProgress();
  const [peers, setPeers] = useState([]);
  const [selected, setSelected] = useState(() => new Set());
  const [message, setMessage] = useState("");
  const [intent, setIntent] = useState(() => normalizeRecommendIntent(defaultIntent));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    setLoading(true);
    setError("");
    setSelected(new Set());
    const nextIntent = normalizeRecommendIntent(defaultIntent);
    setIntent(nextIntent);
    setMessage(nextIntent === "watch_party" ? defaultWatchPartyNote(item?.title) : "");
    listHouseholdPeers()
      .then((data) => {
        if (cancelled) return;
        setPeers(data.items || []);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.message || "Could not load household members.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, item?.tmdb_id, item?.title, defaultIntent]);

  if (!open || !item) return null;

  const copy = recommendModalCopy(intent);

  function togglePeer(id) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectIntent(next) {
    const normalized = normalizeRecommendIntent(next);
    setIntent(normalized);
    if (normalized === "watch_party" && !message.trim()) {
      setMessage(defaultWatchPartyNote(item.title));
    }
  }

  async function handleSend(event) {
    event.preventDefault();
    if (!selected.size) {
      setError("Pick at least one person.");
      return;
    }
    setSending(true);
    setError("");
    let progressId = null;
    try {
      progressId = start({
        label: intent === "watch_party" ? "Sending watch invites" : "Sending recommendations",
        total: selected.size,
        asynchronous: true,
      });
      const result = await createRecommendations({
        to_user_ids: [...selected],
        media_type: item.media_type === "show" ? "show" : "movie",
        title: item.title,
        tmdb_id: item.tmdb_id || null,
        tvdb_id: item.tvdb_id || null,
        rating_key: item.rating_key || item.plex_rating_key || null,
        year: item.year || null,
        poster_url: item.poster_url || null,
        message: message.trim() || null,
        intent,
      });
      update(progressId, selected.size);
      finish(progressId, {
        label:
          intent === "watch_party"
            ? `Invited ${selected.size} to watch together.`
            : `Sent recommendation${selected.size === 1 ? "" : "s"} to ${selected.size}.`,
      });
      onSent?.(result);
      onClose?.();
    } catch (err) {
      const failMessage = err.message || "Could not send recommendation.";
      setError(failMessage);
      finish(progressId, { label: failMessage, state: "error" });
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="recommend-modal-backdrop" data-testid="recommend-modal" onClick={onClose}>
      <div
        className="recommend-modal"
        role="dialog"
        aria-modal="true"
        aria-label={
          intent === "watch_party" ? `Watch ${item.title} together` : `Recommend ${item.title}`
        }
        onClick={(event) => event.stopPropagation()}
      >
        <header className="recommend-modal-header">
          <div>
            <p className="eyebrow">{copy.eyebrow}</p>
            <h2>
              {item.title}
              {item.year ? ` (${item.year})` : ""}
            </h2>
          </div>
          <button type="button" className="ghost" onClick={onClose} data-testid="recommend-modal-close">
            Close
          </button>
        </header>

        <form className="recommend-modal-form" onSubmit={handleSend}>
          <div
            className="recommend-intent-toggle"
            role="group"
            aria-label="Recommendation style"
            data-testid="recommend-intent-toggle"
          >
            <button
              type="button"
              className={`ghost recommend-intent${intent === "recommend" ? " is-active" : ""}`}
              data-testid="recommend-intent-recommend"
              aria-pressed={intent === "recommend"}
              onClick={() => selectIntent("recommend")}
            >
              Recommend
            </button>
            <button
              type="button"
              className={`ghost recommend-intent${intent === "watch_party" ? " is-active" : ""}`}
              data-testid="recommend-intent-watch-party"
              aria-pressed={intent === "watch_party"}
              onClick={() => selectIntent("watch_party")}
            >
              Watch together
            </button>
          </div>

          {loading ? <p className="status status-secondary">Loading household…</p> : null}
          {!loading && !peers.length ? (
            <p className="status status-secondary" data-testid="recommend-no-peers">
              No other household members yet. Enable multi-user and invite someone first.
            </p>
          ) : null}
          {!loading && peers.length ? (
            <ul className="recommend-peer-list" data-testid="recommend-peer-list">
              {peers.map((peer) => {
                const checked = selected.has(peer.id);
                return (
                  <li key={peer.id}>
                    <label className={`recommend-peer ${checked ? "selected" : ""}`}>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => togglePeer(peer.id)}
                        data-testid={`recommend-peer-${peer.id}`}
                      />
                      <span>{peer.display_name}</span>
                    </label>
                  </li>
                );
              })}
            </ul>
          ) : null}

          {intent === "watch_party" ? (
            <div className="recommend-note-chips" data-testid="recommend-note-chips">
              {WATCH_PARTY_NOTE_CHIPS.map((chip) => (
                <button
                  key={chip}
                  type="button"
                  className="ghost recommend-note-chip"
                  onClick={() => setMessage(chip)}
                >
                  {chip}
                </button>
              ))}
            </div>
          ) : null}

          <label className="recommend-note-label">
            <span>{copy.noteHint}</span>
            <textarea
              data-testid="recommend-note"
              value={message}
              maxLength={280}
              rows={2}
              placeholder={copy.notePlaceholder}
              onChange={(event) => setMessage(event.target.value)}
            />
          </label>

          {error ? (
            <p className="status status-error" data-testid="recommend-error">
              {error}
            </p>
          ) : null}

          <div className="recommend-modal-actions">
            <button type="button" className="ghost" onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              data-testid="recommend-send"
              disabled={sending || !peers.length || !selected.size}
            >
              {sending ? copy.sendingLabel : copy.sendLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

import { useEffect, useState } from "react";
import { createRecommendations, listHouseholdPeers } from "../api/client";
import { useBulkActionProgress } from "./BulkActionProgress";

export default function RecommendModal({ item, open, onClose, onSent }) {
  const { start, update, finish } = useBulkActionProgress();
  const [peers, setPeers] = useState([]);
  const [selected, setSelected] = useState(() => new Set());
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    setLoading(true);
    setError("");
    setSelected(new Set());
    setMessage("");
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
  }, [open, item?.tmdb_id, item?.title]);

  if (!open || !item) return null;

  function togglePeer(id) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleSend(event) {
    event.preventDefault();
    if (!selected.size) {
      setError("Pick at least one person.");
      return;
    }
    const progressId = start({
      label: "Sending recommendations",
      total: selected.size,
      asynchronous: true,
    });
    setSending(true);
    setError("");
    try {
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
      });
      update(progressId, selected.size);
      finish(progressId, {
        label: `Sent recommendation${selected.size === 1 ? "" : "s"} to ${selected.size}.`,
      });
      onSent?.(result);
      onClose?.();
    } catch (err) {
      const message = err.message || "Could not send recommendation.";
      setError(message);
      finish(progressId, { label: message, state: "error" });
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
        aria-label={`Recommend ${item.title}`}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="recommend-modal-header">
          <div>
            <p className="eyebrow">Recommend to…</p>
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

          <label className="recommend-note-label">
            <span>Optional note</span>
            <textarea
              data-testid="recommend-note"
              value={message}
              maxLength={280}
              rows={2}
              placeholder="Thought you'd love this…"
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
              {sending ? "Sending…" : "Send recommendation"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

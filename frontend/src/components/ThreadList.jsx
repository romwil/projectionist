import { useMemo, useState } from "react";
import { relativeTime } from "../api/client";
import { filterThreads } from "../lib/threadFilter.js";

export default function ThreadList({
  threads = [],
  activeSessionId,
  onSelect,
  onCreate,
  onDelete,
  compact = false,
  hideHeader = false,
  personaLookup = {},
}) {
  const [confirmId, setConfirmId] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [query, setQuery] = useState("");

  const visibleThreads = useMemo(() => filterThreads(threads, query), [threads, query]);

  async function handleDelete(threadId) {
    if (!onDelete || deletingId) return;
    setDeletingId(threadId);
    try {
      await onDelete(threadId);
      setConfirmId(null);
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className={`thread-list ${compact ? "compact" : ""}`} data-testid="thread-list">
      {hideHeader ? (
        <div className="thread-list-toolbar">
          <button type="button" className="ghost thread-new-btn" data-testid="new-thread" onClick={onCreate}>
            New
          </button>
        </div>
      ) : (
        <div className="thread-list-header">
          <p className="eyebrow">Conversations</p>
          <button type="button" className="ghost thread-new-btn" data-testid="new-thread" onClick={onCreate}>
            New
          </button>
        </div>
      )}

      <label className="thread-search" data-testid="thread-search">
        <span className="sr-only">Search conversations</span>
        <input
          type="search"
          className="thread-search-input"
          data-testid="thread-search-input"
          placeholder="Search threads…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          autoComplete="off"
        />
      </label>

      {threads.length === 0 ? (
        <p className="thread-empty">No conversations yet.</p>
      ) : visibleThreads.length === 0 ? (
        <p className="thread-empty" data-testid="thread-search-empty">
          No conversations match “{query.trim()}”.
        </p>
      ) : (
        <ul className="thread-items">
          {visibleThreads.map((thread) => {
            const isActive = thread.id === activeSessionId;
            const persona = thread.persona_id ? personaLookup[thread.persona_id] : null;
            const confirming = confirmId === thread.id;
            return (
              <li key={thread.id} className={confirming ? "is-confirming-delete" : ""}>
                {confirming ? (
                  <div className="thread-delete-confirm" data-testid={`thread-delete-confirm-${thread.id}`}>
                    <p>Delete this conversation?</p>
                    <div className="thread-delete-confirm-actions">
                      <button
                        type="button"
                        className="ghost"
                        data-testid={`thread-delete-cancel-${thread.id}`}
                        disabled={deletingId === thread.id}
                        onClick={() => setConfirmId(null)}
                      >
                        Keep
                      </button>
                      <button
                        type="button"
                        data-testid={`thread-delete-confirm-btn-${thread.id}`}
                        disabled={deletingId === thread.id}
                        onClick={() => handleDelete(thread.id)}
                      >
                        {deletingId === thread.id ? "Deleting…" : "Delete"}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className={`thread-item-row${isActive ? " active" : ""}`}>
                    <button
                      type="button"
                      className={`thread-item ${isActive ? "active" : ""}`}
                      data-testid={`thread-item-${thread.id}`}
                      onClick={() => onSelect(thread.id)}
                    >
                      <span className="thread-item-title">{thread.thread_title}</span>
                      {persona ? (
                        <span className="thread-persona-badge">
                          {persona.accent_color && (
                            <span className="persona-dot-sm" style={{ background: persona.accent_color }} />
                          )}
                          {persona.name}
                        </span>
                      ) : null}
                      {thread.preview ? <span className="thread-item-preview">{thread.preview}</span> : null}
                      <span className="thread-item-meta">{relativeTime(thread.updated_at)}</span>
                    </button>
                    {onDelete ? (
                      <button
                        type="button"
                        className="ghost thread-delete-btn"
                        data-testid={`thread-delete-${thread.id}`}
                        aria-label={`Delete conversation ${thread.thread_title || ""}`.trim()}
                        onClick={() => setConfirmId(thread.id)}
                      >
                        ✕
                      </button>
                    ) : null}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

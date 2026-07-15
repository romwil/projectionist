import { relativeTime } from "../api/client";

export default function ThreadList({
  threads = [],
  activeSessionId,
  onSelect,
  onCreate,
  compact = false,
  hideHeader = false,
  personaLookup = {},
}) {
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

      {threads.length === 0 ? (
        <p className="thread-empty">No conversations yet.</p>
      ) : (
        <ul className="thread-items">
          {threads.map((thread) => {
            const isActive = thread.id === activeSessionId;
            const persona = thread.persona_id ? personaLookup[thread.persona_id] : null;
            return (
              <li key={thread.id}>
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
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

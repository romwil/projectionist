/**
 * Circular curator/agent mark shown beside assistant messages.
 */
export default function AgentAvatar({ name = "Curator", streaming = false }) {
  const label = String(name || "Curator").trim() || "Curator";
  const initial = label.charAt(0).toUpperCase() || "C";
  return (
    <div
      className={`agent-avatar${streaming ? " is-streaming" : ""}`}
      data-testid="agent-avatar"
      title={label}
      aria-label={label}
    >
      <span className="agent-avatar-initial" aria-hidden="true">
        {initial}
      </span>
    </div>
  );
}

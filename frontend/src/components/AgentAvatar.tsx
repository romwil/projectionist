import { GENERIC_CURATOR_NAME } from "../lib/curatorName";
type AgentAvatarProps = {
  name?: string;
  streaming?: boolean;
};

/**
 * Circular curator/agent mark shown beside assistant messages.
 */
export default function AgentAvatar({ name = GENERIC_CURATOR_NAME, streaming = false }: AgentAvatarProps) {
  const label = String(name || GENERIC_CURATOR_NAME).trim() || GENERIC_CURATOR_NAME;
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

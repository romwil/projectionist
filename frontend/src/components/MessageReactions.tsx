type MessageReactionsProps = {
  messageId?: string | number;
  sessionId?: string;
  initialFeedback?: string | null;
  onFeedbackChange?: (messageId: string | number | undefined, next: string | null) => void;
};

export default function MessageReactions({
  messageId,
  sessionId: _sessionId,
  initialFeedback,
  onFeedbackChange,
}: MessageReactionsProps) {
  const activeFeedback = initialFeedback ?? null;

  function handleClick(feedback: string) {
    const next = activeFeedback === feedback ? null : feedback;
    onFeedbackChange?.(messageId, next);
  }

  return (
    <div className="message-reactions" data-testid="message-reactions">
      <button
        type="button"
        className={`message-reaction-btn ghost${activeFeedback === "helpful" ? " is-active" : ""}`}
        data-testid="feedback-helpful"
        aria-label="Helpful"
        aria-pressed={activeFeedback === "helpful"}
        title="Helpful"
        onClick={() => handleClick("helpful")}
      >
        <span aria-hidden="true">👍</span>
      </button>
      <button
        type="button"
        className={`message-reaction-btn ghost${activeFeedback === "not_helpful" ? " is-active" : ""}`}
        data-testid="feedback-not-helpful"
        aria-label="Not helpful"
        aria-pressed={activeFeedback === "not_helpful"}
        title="Not helpful"
        onClick={() => handleClick("not_helpful")}
      >
        <span aria-hidden="true">👎</span>
      </button>
    </div>
  );
}

type BufferingIndicatorProps = {
  label?: string;
  testId?: string;
  variant?: string;
  className?: string;
};

/**
 * Library Play buffering chrome — film-reel mark + obvious label.
 * Used while waiting for frames after seek or underrun. Not a faint “Loading…”.
 */
export default function BufferingIndicator({
  label = "Buffering",
  testId = "library-buffering-chip",
  variant = "chip",
  className = "",
}: BufferingIndicatorProps) {
  const showLabel = Boolean(label);
  return (
    <div
      className={`buffering-indicator buffering-indicator--${variant}${className ? ` ${className}` : ""}`}
      role="status"
      aria-live="polite"
      aria-busy="true"
      data-testid={testId}
    >
      <span className="buffering-reel" aria-hidden="true">
        <span className="buffering-reel-ring" />
        <span className="buffering-reel-sprockets" />
        <span className="buffering-reel-hub" />
      </span>
      {showLabel ? <p className="buffering-indicator-label">{label}</p> : null}
    </div>
  );
}

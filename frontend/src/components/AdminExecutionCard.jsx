import {
  adminCanCancel,
  adminDisplayPercent,
  adminItemStatusLabel,
  adminPhaseLabel,
  adminProgressLine,
  adminSecondsAgo,
  adminShouldShowCard,
} from "../lib/adminExecution.js";

/**
 * Shared Sonarr-missing-style job card: phase, counts, current item, last error,
 * optional title queue, cancel remaining.
 */
export default function AdminExecutionCard({
  job,
  testId = "admin-execution",
  phaseLabels,
  extraNote,
  children,
  onCancel,
  cancelLabel = "Cancel remaining",
  showItems = true,
}) {
  if (!adminShouldShowCard(job)) return null;
  const percent = adminDisplayPercent(job);
  const execution = job?.execution || {};
  const items = Array.isArray(job?.items) ? job.items : [];
  const showCounts = Number(execution.total) > 0;
  const current = execution.current || job?.current;
  const lastError = execution.last_error || job?.error;
  const secondsAgo = adminSecondsAgo(execution.seconds_since_last_completion);

  return (
    <div className="library-sync-progress" data-testid={testId}>
      <p className="library-sync-progress-headline">
        <strong>{adminPhaseLabel(job?.phase, phaseLabels)}</strong>
        {typeof percent === "number" ? ` · ${percent}%` : ""}
      </p>
      {adminProgressLine(job) ? (
        <p className="library-sync-progress-detail status status-secondary">
          {adminProgressLine(job)}
        </p>
      ) : null}
      {showCounts ? (
        <div className="sonarr-missing-counts admin-execution-counts" data-testid={`${testId}-execution`}>
          <span>{Number(execution.queued) || 0} queued</span>
          <span>{Number(execution.running) || 0} running</span>
          <span>{Number(execution.completed) || 0} completed</span>
          {Number(execution.skipped) ? <span>{Number(execution.skipped)} skipped</span> : null}
          <span data-tone={Number(execution.failed) ? "failed" : undefined}>
            {Number(execution.failed) || 0} failed
          </span>
          {Number(execution.cancelled) ? <span>{Number(execution.cancelled)} cancelled</span> : null}
        </div>
      ) : null}
      {current ? (
        <p className="wizard-note" data-testid={`${testId}-current`}>
          Current: {current.message || current.name} ({current.status})
        </p>
      ) : null}
      {secondsAgo ? <p className="wizard-note">{secondsAgo}</p> : null}
      {lastError ? (
        <p className="status status-error" data-testid={`${testId}-last-error`}>
          Last error: {lastError}
        </p>
      ) : null}
      {extraNote && job?.busy ? <p className="wizard-note">{extraNote}</p> : null}
      {showItems && items.length ? (
        <ul className="admin-execution-items" data-testid={`${testId}-items`}>
          {items.map((item) => (
            <li key={String(item.id)} data-status={item.status} data-outcome={item.outcome || ""}>
              <span>{item.title || item.name || `Item ${item.id}`}</span>
              <span className="admin-execution-item-status">{adminItemStatusLabel(item)}</span>
              {item.error ? <span className="status status-error"> — {item.error}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
      {typeof percent === "number" && job?.busy ? (
        <div
          className="library-sync-progress-bar"
          role="progressbar"
          aria-valuenow={percent}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <span className="library-sync-progress-fill" style={{ width: `${percent}%` }} />
        </div>
      ) : null}
      {onCancel && adminCanCancel(job) ? (
        <div className="config-actions">
          <button
            type="button"
            className="ghost"
            data-testid={`${testId}-cancel`}
            onClick={onCancel}
          >
            {cancelLabel}
          </button>
        </div>
      ) : null}
      {children}
    </div>
  );
}

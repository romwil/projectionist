import { collectRepairItems } from "../../lib/rematchStudio.js";

/**
 * Failed search / register rows with rematch, skip, retry, Investigate.
 * Human copy only — never a JSON dump.
 */
export default function RepairMiss({
  radarrRegister,
  sonarrMissing,
  onRematch,
  onRetry,
  onSkip,
  onInvestigate,
  retryingId,
  skippingId,
}) {
  const items = collectRepairItems(radarrRegister, sonarrMissing);
  if (!items.length) return null;

  return (
    <section className="config-section" data-testid="repair-miss-card">
      <h2>Repair the miss</h2>
      <p className="wizard-note">
        A failed search or register is a miss to repair — rematch, skip, retry, or Investigate.
        No raw JSON.
      </p>
      {items.map((item) => (
        <div
          key={`${item.source}-${item.id}`}
          data-testid={`repair-miss-${item.source}-${item.id}`}
          style={{
            marginTop: 16,
            paddingTop: 16,
            borderTop: "1px solid var(--border-subtle)",
          }}
        >
          <p>
            <strong>{item.title}</strong>
          </p>
          <p className="status status-secondary" data-testid={`repair-miss-copy-${item.id}`}>
            {item.message}
          </p>
          <div className="config-actions">
            {(item.actions || []).includes("rematch") ? (
              <button
                type="button"
                className="ghost"
                data-testid={`repair-rematch-${item.id}`}
                onClick={() => onRematch?.(item)}
              >
                Rematch
              </button>
            ) : null}
            {(item.actions || []).includes("retry") ? (
              <button
                type="button"
                className="ghost"
                data-testid={`repair-retry-${item.id}`}
                onClick={() => onRetry?.(item)}
                disabled={String(retryingId) === String(item.id)}
              >
                {String(retryingId) === String(item.id) ? "Retrying…" : "Retry"}
              </button>
            ) : null}
            {(item.actions || []).includes("investigate") ? (
              <button
                type="button"
                className="ghost"
                data-testid={`repair-investigate-${item.id}`}
                onClick={() => onInvestigate?.(item)}
              >
                Investigate
              </button>
            ) : null}
            {(item.actions || []).includes("skip") ? (
              <button
                type="button"
                className="ghost"
                data-testid={`repair-skip-${item.id}`}
                onClick={() => onSkip?.(item)}
                disabled={String(skippingId) === String(item.id)}
              >
                Skip
              </button>
            ) : null}
          </div>
        </div>
      ))}
    </section>
  );
}

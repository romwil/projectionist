import { collectRepairItems, tmdbMovieUrl } from "../../lib/rematchStudio.js";

type RepairItem = {
  id?: string | number;
  source?: string;
  title?: string;
  year?: number | string | null;
  kind?: string;
  message?: string;
  actions?: string[];
  plexTmdbId?: string | number | null;
  radarrTmdbId?: string | number | null;
  folderPath?: string;
};

type RepairMissProps = {
  radarrRegister?: unknown;
  sonarrMissing?: unknown;
  onRematch?: (item: RepairItem) => void;
  onRetry?: (item: RepairItem) => void | Promise<void>;
  onSkip?: (item: RepairItem) => void | Promise<void>;
  onInvestigate?: (item: Record<string, unknown>) => void;
  retryingId?: string | number;
  skippingId?: string | number;
};

function TmdbIdLine({ label, id, testId }: { label: string; id?: string | number | null; testId: string }) {
  if (id == null || id === "" || Number(id) <= 0) return null;
  const href = tmdbMovieUrl(id);
  return (
    <p className="status status-secondary" data-testid={testId}>
      {label}:{" "}
      {href ? (
        <a href={href} target="_blank" rel="noreferrer">
          {String(id)}
        </a>
      ) : (
        String(id)
      )}
    </p>
  );
}

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
}: RepairMissProps) {
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
          {String(item.kind || "").toLowerCase() === "path_conflict" ? (
            <div data-testid={`repair-miss-identity-${item.id}`}>
              <TmdbIdLine
                label="Plex TMDB id"
                id={item.plexTmdbId}
                testId={`repair-miss-plex-tmdb-${item.id}`}
              />
              <TmdbIdLine
                label="Radarr TMDB id"
                id={item.radarrTmdbId}
                testId={`repair-miss-radarr-tmdb-${item.id}`}
              />
              {item.folderPath ? (
                <p className="status status-secondary" data-testid={`repair-miss-folder-${item.id}`}>
                  Folder path: {item.folderPath}
                </p>
              ) : null}
            </div>
          ) : null}
          <div className="config-actions">
            {(item.actions || []).includes("rematch") ? (
              <button
                type="button"
                className="ghost"
                data-testid={`repair-rematch-${item.id}`}
                onClick={() => onRematch?.(item)}
              >
                Open Rematch studio
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

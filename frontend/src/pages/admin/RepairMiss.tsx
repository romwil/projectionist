import {
  collectRepairItems,
  identityKindLabel,
  primaryRepairAction,
  tmdbMovieUrl,
} from "../../lib/rematchStudio.js";

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
  softMatch?: boolean;
  sameTitle?: boolean;
};

type RepairMissProps = {
  radarrRegister?: unknown;
  sonarrMissing?: unknown;
  onRematch?: (item: RepairItem) => void;
  onRetry?: (item: RepairItem) => void | Promise<void>;
  onSkip?: (item: RepairItem) => void | Promise<void>;
  onInvestigate?: (item: Record<string, unknown>) => void;
  onUseRadarr?: (item: RepairItem) => void | Promise<void>;
  onUsePlex?: (item: RepairItem) => void | Promise<void>;
  onRecheckAll?: () => void | Promise<void>;
  retryingId?: string | number;
  skippingId?: string | number;
  actingId?: string | number;
  rechecking?: boolean;
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

function displayTitle(item: RepairItem) {
  const title = String(item.title || "This title");
  if (item.year != null && item.year !== "" && !/\(\d{4}\)\s*$/.test(title)) {
    return `${title} (${item.year})`;
  }
  return title;
}

function actionClass(action: string, actions?: string[]) {
  return primaryRepairAction(actions) === action ? "primary" : "ghost";
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
  onUseRadarr,
  onUsePlex,
  onRecheckAll,
  retryingId,
  skippingId,
  actingId,
  rechecking,
}: RepairMissProps) {
  const items = collectRepairItems(radarrRegister, sonarrMissing);
  if (!items.length) return null;
  const pathConflicts = items.filter((item) => String(item.kind || "").toLowerCase() === "path_conflict");

  return (
    <section className="config-section" data-testid="repair-miss-card">
      <h2>Repair the miss</h2>
      <p className="wizard-note">
        A failed search or register is a miss to repair — re-check after an external fix, adopt an
        identity when title/year soft-match, or open Rematch studio. No raw JSON.
      </p>
      {pathConflicts.length && onRecheckAll ? (
        <div className="config-actions repair-miss-toolbar">
          <button
            type="button"
            className="primary"
            data-testid="repair-recheck-all"
            onClick={() => onRecheckAll()}
            disabled={Boolean(rechecking)}
          >
            {rechecking ? "Re-checking…" : "Re-check all path conflicts"}
          </button>
        </div>
      ) : null}
      {items.map((item) => (
        <div
          key={`${item.source}-${item.id}`}
          className="repair-miss-row"
          data-testid={`repair-miss-${item.source}-${item.id}`}
        >
          <h3 className="repair-miss-title" data-testid={`repair-miss-title-${item.id}`}>
            {displayTitle(item)}
          </h3>
          {String(item.kind || "").toLowerCase() === "path_conflict" ? (
            <p className="wizard-note" data-testid={`repair-miss-kind-${item.id}`}>
              {identityKindLabel(String(item.kind), item.sameTitle || item.softMatch)}
            </p>
          ) : null}
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
            {(item.actions || []).includes("use_radarr") ? (
              <button
                type="button"
                className={actionClass("use_radarr", item.actions)}
                data-testid={`repair-use-radarr-${item.id}`}
                onClick={() => onUseRadarr?.(item)}
                disabled={String(actingId) === `use-radarr-${item.id}`}
              >
                {String(actingId) === `use-radarr-${item.id}` ? "Adopting…" : "Use Radarr’s identity"}
              </button>
            ) : null}
            {(item.actions || []).includes("use_plex") ? (
              <button
                type="button"
                className="ghost"
                data-testid={`repair-use-plex-${item.id}`}
                onClick={() => onUsePlex?.(item)}
                disabled={String(actingId) === `use-plex-${item.id}`}
              >
                {String(actingId) === `use-plex-${item.id}` ? "Adopting…" : "Use Plex’s identity"}
              </button>
            ) : null}
            {(item.actions || []).includes("retry") ? (
              <button
                type="button"
                className={actionClass("retry", item.actions)}
                data-testid={`repair-retry-${item.id}`}
                onClick={() => onRetry?.(item)}
                disabled={String(retryingId) === String(item.id)}
              >
                {String(retryingId) === String(item.id) ? "Retrying…" : "Retry"}
              </button>
            ) : null}
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
            {(item.actions || []).includes("investigate") ? (
              <button
                type="button"
                className={actionClass("investigate", item.actions)}
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

import {
  adminCanCancel,
  adminCompletionCopy,
  adminDisplayPercent,
  adminItemStatusLabel,
  adminPhaseLabel,
  adminProgressLine,
  adminShouldShowCard,
} from "../lib/adminExecution.js";
import {
  primaryRepairAction,
  repairActionsFor,
  titlesSoftMatch,
  tmdbMovieUrl,
} from "../lib/rematchStudio.js";

type AdminExecutionCurrent = {
  message?: string;
  name?: string;
  status?: string;
};

type AdminExecution = {
  total?: number;
  queued?: number;
  running?: number;
  completed?: number;
  skipped?: number;
  failed?: number;
  cancelled?: number;
  current?: AdminExecutionCurrent;
  last_error?: string;
};

type AdminExecutionItem = {
  id?: string | number;
  title?: string;
  name?: string;
  status?: string;
  outcome?: string;
  error?: string;
  plex_tmdb_id?: string | number | null;
  radarr_tmdb_id?: string | number | null;
  folder_path?: string;
  soft_match?: boolean;
  same_title?: boolean;
  plex_title?: string;
  radarr_title?: string;
  year?: number | string | null;
};

type AdminJob = {
  execution?: AdminExecution;
  items?: AdminExecutionItem[];
  current?: AdminExecutionCurrent;
  error?: string;
  phase?: string;
  busy?: boolean;
};

type ItemHandlers = {
  onRematch?: (item: AdminExecutionItem) => void;
  onRetry?: (item: AdminExecutionItem) => void | Promise<void>;
  onSkip?: (item: AdminExecutionItem) => void | Promise<void>;
  onUseRadarr?: (item: AdminExecutionItem) => void | Promise<void>;
  onUsePlex?: (item: AdminExecutionItem) => void | Promise<void>;
  retryingId?: string | number;
  skippingId?: string | number;
  actingId?: string | number;
};

type AdminExecutionCardProps = {
  job?: AdminJob | null;
  testId?: string;
  phaseLabels?: Record<string, string>;
  extraNote?: React.ReactNode;
  children?: React.ReactNode;
  onCancel?: (...args: any[]) => void;
  cancelLabel?: string;
  showItems?: boolean;
  itemActions?: ItemHandlers;
};

function softForItem(item: AdminExecutionItem) {
  if (item.soft_match) return true;
  return titlesSoftMatch(item.plex_title || item.title, item.radarr_title);
}

function actionsForItem(item: AdminExecutionItem) {
  const outcome = String(item.outcome || "").toLowerCase();
  if (outcome !== "path_conflict" && String(item.status || "").toLowerCase() !== "failed") {
    return [] as string[];
  }
  const kind = outcome === "path_conflict" ? "path_conflict" : "failed";
  return repairActionsFor(kind, "movie", softForItem(item));
}

function TmdbLink({ id }: { id?: string | number | null }) {
  if (id == null || id === "" || Number(id) <= 0) return null;
  const href = tmdbMovieUrl(id);
  if (!href) return <span>{String(id)}</span>;
  return (
    <a href={href} target="_blank" rel="noreferrer">
      {String(id)}
    </a>
  );
}

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
  itemActions,
}: AdminExecutionCardProps) {
  if (!adminShouldShowCard(job)) return null;
  const percent = adminDisplayPercent(job);
  const execution = job?.execution || {};
  const items = Array.isArray(job?.items) ? job.items : [];
  const showCounts = Number(execution.total) > 0;
  const current = execution.current || job?.current;
  const lastError = execution.last_error || job?.error;
  const completion = adminCompletionCopy(job);

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
      {completion ? (
        <p className="wizard-note" data-testid={`${testId}-completion`}>
          {completion}
        </p>
      ) : null}
      {lastError ? (
        <p className="status status-error" data-testid={`${testId}-last-error`}>
          Last error: {lastError}
        </p>
      ) : null}
      {extraNote && job?.busy ? <p className="wizard-note">{extraNote}</p> : null}
      {showItems && items.length ? (
        <ul className="admin-execution-items" data-testid={`${testId}-items`}>
          {items.map((item: AdminExecutionItem) => {
            const actions = itemActions ? actionsForItem(item) : [];
            const primary = primaryRepairAction(actions);
            const isConflict = String(item.outcome || "").toLowerCase() === "path_conflict";
            return (
              <li
                key={String(item.id)}
                data-status={item.status}
                data-outcome={item.outcome || ""}
                data-testid={`${testId}-item-${item.id}`}
              >
                <div className="admin-execution-item-head">
                  <span>{item.title || item.name || `Item ${item.id}`}</span>
                  <span className="admin-execution-item-status">{adminItemStatusLabel(item)}</span>
                </div>
                {item.error ? <span className="status status-error"> — {item.error}</span> : null}
                {isConflict ? (
                  <div className="admin-execution-item-identity" data-testid={`${testId}-identity-${item.id}`}>
                    {item.plex_tmdb_id != null ? (
                      <p className="status status-secondary">
                        Plex TMDB id: <TmdbLink id={item.plex_tmdb_id} />
                      </p>
                    ) : null}
                    {item.radarr_tmdb_id != null ? (
                      <p className="status status-secondary">
                        Radarr TMDB id: <TmdbLink id={item.radarr_tmdb_id} />
                      </p>
                    ) : null}
                    {item.folder_path ? (
                      <p className="status status-secondary">Folder path: {item.folder_path}</p>
                    ) : null}
                  </div>
                ) : null}
                {actions.length ? (
                  <div className="config-actions admin-execution-item-actions">
                    {actions.includes("use_radarr") ? (
                      <button
                        type="button"
                        className={primary === "use_radarr" ? "primary" : "ghost"}
                        data-testid={`${testId}-use-radarr-${item.id}`}
                        onClick={() => itemActions?.onUseRadarr?.(item)}
                        disabled={String(itemActions?.actingId) === `use-radarr-${item.id}`}
                      >
                        Use Radarr’s identity
                      </button>
                    ) : null}
                    {actions.includes("use_plex") ? (
                      <button
                        type="button"
                        className="ghost"
                        data-testid={`${testId}-use-plex-${item.id}`}
                        onClick={() => itemActions?.onUsePlex?.(item)}
                        disabled={String(itemActions?.actingId) === `use-plex-${item.id}`}
                      >
                        Use Plex’s identity
                      </button>
                    ) : null}
                    {actions.includes("retry") ? (
                      <button
                        type="button"
                        className={primary === "retry" ? "primary" : "ghost"}
                        data-testid={`${testId}-retry-${item.id}`}
                        onClick={() => itemActions?.onRetry?.(item)}
                        disabled={String(itemActions?.retryingId) === String(item.id)}
                      >
                        Retry
                      </button>
                    ) : null}
                    {actions.includes("rematch") ? (
                      <button
                        type="button"
                        className="ghost"
                        data-testid={`${testId}-rematch-${item.id}`}
                        onClick={() => itemActions?.onRematch?.(item)}
                      >
                        Open Rematch studio
                      </button>
                    ) : null}
                    {actions.includes("skip") ? (
                      <button
                        type="button"
                        className="ghost"
                        data-testid={`${testId}-skip-${item.id}`}
                        onClick={() => itemActions?.onSkip?.(item)}
                        disabled={String(itemActions?.skippingId) === String(item.id)}
                      >
                        Skip
                      </button>
                    ) : null}
                  </div>
                ) : null}
              </li>
            );
          })}
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

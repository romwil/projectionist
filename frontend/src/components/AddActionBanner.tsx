import { serviceLabelForTarget, tokenConfirmButtonLabel, tokenConfirmPrompt } from "../lib/addActions";

type AddProgress = {
  current?: number;
  total?: number;
};

type PendingAdd = {
  item?: { title?: string };
  target?: string;
};

type PendingBulk = {
  items?: unknown[];
  target?: string;
};

type AddActionBannerProps = {
  pendingAdd?: PendingAdd | null;
  pendingBulk?: PendingBulk | null;
  pendingTokens?: unknown[] | null;
  inProgress?: boolean;
  progress?: AddProgress | null;
  onConfirm?: (...args: any[]) => void;
  onCancel?: (...args: any[]) => void;
};

export default function AddActionBanner({
  pendingAdd,
  pendingBulk,
  pendingTokens,
  inProgress,
  progress,
  onConfirm,
  onCancel,
}: AddActionBannerProps) {
  if (pendingBulk) {
    const { items, target } = pendingBulk;
    const service = serviceLabelForTarget(target);
    const count = items?.length ?? 0;
    const progressLabel =
      inProgress && progress?.total
        ? target === "seerr"
          ? `Requesting ${Math.min(progress.current ?? 0, progress.total)} of ${progress.total}…`
          : `Adding ${Math.min(progress.current ?? 0, progress.total)} of ${progress.total}…`
        : null;

    return (
      <div className="add-action-banner" data-testid="bulk-add-banner" role="alertdialog" aria-modal="true">
        <p data-testid="bulk-add-prompt">
          {target === "seerr" ? (
            <>
              Request all <strong>{count}</strong> titles in Seerr?
            </>
          ) : (
            <>
              Add all <strong>{count}</strong> titles to {service}?
            </>
          )}
        </p>
        {progressLabel ? <p className="bulk-add-progress">{progressLabel}</p> : null}
        <div className="add-action-buttons">
          <button type="button" data-testid="bulk-add-confirm" onClick={onConfirm} disabled={inProgress}>
            {inProgress ? "Adding…" : `Confirm all ${count}`}
          </button>
          <button type="button" className="ghost" data-testid="bulk-add-cancel" onClick={onCancel} disabled={inProgress}>
            Cancel
          </button>
        </div>
      </div>
    );
  }

  if (pendingTokens?.length) {
    const count = pendingTokens.length;
    const progressLabel =
      inProgress && progress?.total
        ? `Confirming ${Math.min(progress.current ?? 0, progress.total)} of ${progress.total}…`
        : null;

    return (
      <div className="add-action-banner" data-testid="token-confirm-banner" role="alertdialog" aria-modal="true">
        <p data-testid="token-confirm-prompt">
          {(() => {
            const text = tokenConfirmPrompt(count, pendingTokens);
            const match = text.match(/^Confirm all (\d+) (.+)$/);
            if (!match) return text;
            return (
              <>
                Confirm all <strong>{match[1]}</strong> {match[2]}
              </>
            );
          })()}
        </p>
        {progressLabel ? <p className="bulk-add-progress">{progressLabel}</p> : null}
        <div className="add-action-buttons">
          <button type="button" data-testid="token-confirm-all" onClick={onConfirm} disabled={inProgress}>
            {inProgress ? "Confirming…" : tokenConfirmButtonLabel(count, pendingTokens)}
          </button>
          <button type="button" className="ghost" data-testid="token-confirm-cancel" onClick={onCancel} disabled={inProgress}>
            Cancel
          </button>
        </div>
      </div>
    );
  }

  if (!pendingAdd) return null;

  const { item, target } = pendingAdd;
  const label = item?.title || "this title";
  const service = serviceLabelForTarget(target);

  return (
    <div className="add-action-banner" data-testid="add-action-banner" role="alertdialog" aria-modal="true">
      <p data-testid="add-action-prompt">
        {target === "seerr" ? (
          <>
            Request <strong>{label}</strong> in Seerr?
          </>
        ) : (
          <>
            Add <strong>{label}</strong> to {service}?
          </>
        )}
      </p>
      <div className="add-action-buttons">
        <button
          type="button"
          data-testid="add-action-confirm"
          onClick={onConfirm}
          disabled={inProgress}
        >
          {inProgress
            ? target === "seerr"
              ? "Requesting…"
              : "Adding…"
            : target === "seerr"
              ? "Request in Seerr"
              : `Add to ${service}`}
        </button>
        <button type="button" className="ghost" data-testid="add-action-cancel" onClick={onCancel} disabled={inProgress}>
          Cancel
        </button>
      </div>
    </div>
  );
}

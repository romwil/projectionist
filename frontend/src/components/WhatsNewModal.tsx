import { Link } from "react-router-dom";
import ReleaseNotesPanel from "./ReleaseNotesPanel";

/** Props for WhatsNewModal. `any` = API/handler bags until Wave 4 client generics. */
type WhatsNewModalProps = {
  open?: boolean;
  version?: any;
  release?: any;
  onDismiss?: (...args: any[]) => void;
  onReadFull?: (...args: any[]) => void;
};

export default function WhatsNewModal({ open, version, release, onDismiss, onReadFull }: WhatsNewModalProps) {
  if (!open || !version) return null;

  return (
    <div
      className="whats-new-backdrop"
      data-testid="whats-new-modal"
      onClick={onDismiss}
    >
      <div
        className="whats-new-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="whats-new-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="whats-new-header">
          <h2 id="whats-new-title">What’s new in {version}</h2>
          <button
            type="button"
            className="ghost whats-new-close"
            onClick={onDismiss}
            aria-label="Close"
            data-testid="whats-new-close"
          >
            ✕
          </button>
        </div>

        <div className="whats-new-body">
          {release ? (
            <ReleaseNotesPanel releases={[release]} preferHighlights testId="whats-new-notes" />
          ) : (
            <p className="status status-secondary" data-testid="whats-new-fallback">
              Projectionist {version} is ready. Open About for the full release history.
            </p>
          )}
        </div>

        <div className="whats-new-actions">
          <button
            type="button"
            className="primary"
            data-testid="whats-new-got-it"
            onClick={onDismiss}
          >
            Got it
          </button>
          <Link
            to="/about#release-notes"
            className="ghost"
            data-testid="whats-new-read-full"
            onClick={onReadFull}
          >
            Read full notes
          </Link>
        </div>
      </div>
    </div>
  );
}

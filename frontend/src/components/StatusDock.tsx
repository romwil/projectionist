import { useEffect, useRef, useState } from "react";
import { relativeTime } from "../api/client";
import { TITLE_CARD_DRAG_MIME, readTitleCardDragData, statusDockDropHint } from "../lib/easterEggs.js";
import { formatSyncJobStatus, friendlyProgressMessage } from "../lib/jobProgress.js";
import { isSyncChimeMuted, playSyncChime, setSyncChimeMuted } from "../lib/syncChime";
import AddActionBanner from "./AddActionBanner";
import InlineAlert from "./InlineAlert";

const JOB_ICONS = {
  library_sync: "↻",
  default: "⧉",
};

function jobIcon(job: any) {
  return (JOB_ICONS as any)[job.job_type] || JOB_ICONS.default;
}

function personaFlavor(job: any, jobStatusPhrases: any[] = []) {
  if (!jobStatusPhrases.length) return "";
  const phraseIndex = Math.abs(Number(job.id?.length || 0)) % jobStatusPhrases.length;
  return jobStatusPhrases[phraseIndex] || "";
}

function jobLabel(job: any, jobStatusPhrases: any[] = []) {
  // Live phase / count / % always wins over persona flavor while a job is active.
  if (job.status === "running" || job.status === "queued") {
    const live = formatSyncJobStatus(job);
    const flavor = personaFlavor(job, jobStatusPhrases);
    if (live && flavor && !live.toLowerCase().includes(flavor.toLowerCase())) {
      return `${live} · ${flavor}`;
    }
    return live || "Library sync…";
  }

  const progress = job.progress || {};
  const progressMessage = friendlyProgressMessage(
    progress.message,
    progress.phase,
    job.job_type,
  );
  const status = job.status === "failed" ? "Failed" : "Done";
  return `${status}: ${progressMessage}`;
}

/** Props for AddProgress. `any` = API/handler bags until Wave 4 client generics. */
type AddProgressProps = {
  progress?: any;
};

function AddProgress({ progress }: AddProgressProps) {
  if (!progress?.total) return null;
  const current = Math.min(progress.current || 0, progress.total);
  const pct = Math.round((current / progress.total) * 100);
  const title = progress.title ? ` — ${progress.title}` : "";

  return (
    <div className="status-dock-progress" data-testid="status-dock-progress">
      <p className="status-dock-progress-label">
        Adding {current} of {progress.total}
        {title}…
      </p>
      <div className="status-dock-progress-bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <span className="status-dock-progress-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function isTitleCardDrag(event: any) {
  const types = event?.dataTransfer?.types;
  if (!types) return false;
  return Array.from(types).includes(TITLE_CARD_DRAG_MIME);
}

/** Props for StatusDock. `any` = API/handler bags until Wave 4 client generics. */
type StatusDockProps = {
  jobs?: any;
  jobStatusPhrases?: any;
  pendingAdd?: any;
  pendingBulk?: any;
  pendingTokens?: any;
  addInProgress?: any;
  addProgress?: any;
  addFeedback?: any;
  onConfirm?: (...args: any[]) => void;
  onCancel?: (...args: any[]) => void;
  onDismissFeedback?: (...args: any[]) => void;
  onDropTitle?: (...args: any[]) => void;
  radarrConnected?: any;
  sonarrConnected?: any;
};

export default function StatusDock({
  jobs = [],
  jobStatusPhrases = [],
  pendingAdd,
  pendingBulk,
  pendingTokens,
  addInProgress = false,
  addProgress,
  addFeedback,
  onConfirm,
  onCancel,
  onDismissFeedback,
  onDropTitle,
  radarrConnected = false,
  sonarrConnected = false,
}: StatusDockProps) {
  const [chimeMuted, setChimeMuted] = useState(() => isSyncChimeMuted());
  const [dropActive, setDropActive] = useState(false);
  const [cardDragging, setCardDragging] = useState(false);
  const jobStatusRef = useRef(new Map());

  const dropEnabled = Boolean(onDropTitle && (radarrConnected || sonarrConnected));

  useEffect(() => {
    for (const job of jobs) {
      const previous = jobStatusRef.current.get(job.id);
      if (
        job.job_type === "library_sync" &&
        previous &&
        (previous === "running" || previous === "queued") &&
        (job.status === "completed" || job.status === "done")
      ) {
        playSyncChime();
      }
      jobStatusRef.current.set(job.id, job.status);
    }
  }, [jobs]);

  useEffect(() => {
    if (!dropEnabled) {
      setCardDragging(false);
      setDropActive(false);
      return undefined;
    }

    function onDragStart(event: any) {
      if (isTitleCardDrag(event)) setCardDragging(true);
    }
    function onDragEnd() {
      setCardDragging(false);
      setDropActive(false);
    }

    document.addEventListener("dragstart", onDragStart, true);
    document.addEventListener("dragend", onDragEnd, true);
    return () => {
      document.removeEventListener("dragstart", onDragStart, true);
      document.removeEventListener("dragend", onDragEnd, true);
    };
  }, [dropEnabled]);

  const hasPendingAction = Boolean(pendingAdd || pendingBulk || pendingTokens?.length);
  const activeJobs = jobs.filter((job: any) => job.status === "running" || job.status === "queued");
  const hasJobs = activeJobs.length > 0;
  const hasFeedback = Boolean(addFeedback?.message);
  const showAddBanner = hasPendingAction && !addInProgress;
  const showDropHint = dropEnabled && (cardDragging || dropActive);
  const hasContent = hasJobs || showAddBanner || addInProgress || hasFeedback;
  const dropHint = statusDockDropHint({ radarrConnected, sonarrConnected });

  if (!hasContent && !showDropHint) {
    return null;
  }

  function toggleChimeMute() {
    const next = !chimeMuted;
    setChimeMuted(next);
    setSyncChimeMuted(next);
  }

  return (
    <div
      className={`status-dock ${dropActive || showDropHint ? "drop-ready" : ""} ${dropActive ? "drop-active" : ""}`}
      data-testid="status-dock"
      onDragOver={
        dropEnabled
          ? (event) => {
              event.preventDefault();
              setDropActive(true);
            }
          : undefined
      }
      onDragLeave={
        dropEnabled
          ? () => {
              setDropActive(false);
            }
          : undefined
      }
      onDrop={
        dropEnabled
          ? (event) => {
              event.preventDefault();
              setDropActive(false);
              setCardDragging(false);
              const item = readTitleCardDragData(event);
              if (item) onDropTitle?.(item);
            }
          : undefined
      }
    >
      {hasJobs ? (
        <div className="status-dock-jobs" data-testid="status-dock-jobs">
          {activeJobs.slice(0, 4).map((job: any) => (
            <div key={job.id} className={`status-dock-job status-${job.status}`}>
              <span className="status-dock-job-icon">{jobIcon(job)}</span>
              <div className="status-dock-job-body">
                <span className="status-dock-job-label">{jobLabel(job, jobStatusPhrases)}</span>
                <span className="status-dock-job-time">{relativeTime(job.created_at)}</span>
                {showDropHint ? (
                  <span className="status-dock-drop-hint status-dock-drop-hint-inline" data-testid="status-dock-drop-hint">
                    {dropHint}
                  </span>
                ) : null}
              </div>
            </div>
          ))}
          <button
            type="button"
            className="ghost status-dock-chime-toggle"
            data-testid="sync-chime-toggle"
            onClick={toggleChimeMute}
            title={chimeMuted ? "Unmute sync chime" : "Mute sync chime"}
            aria-label={chimeMuted ? "Unmute sync chime" : "Mute sync chime"}
          >
            {chimeMuted ? "🔕" : "🔔"}
          </button>
        </div>
      ) : null}

      {addInProgress ? <AddProgress progress={addProgress} /> : null}

      {showAddBanner ? (
        <AddActionBanner
          pendingAdd={pendingAdd}
          pendingBulk={pendingBulk}
          pendingTokens={pendingTokens}
          inProgress={false}
          progress={addProgress}
          onConfirm={onConfirm}
          onCancel={onCancel}
        />
      ) : null}

      {hasFeedback ? (
        <InlineAlert
          type={addFeedback.type}
          message={addFeedback.message}
          testId="add-action-feedback"
          onDismiss={onDismissFeedback}
        />
      ) : null}

      {showDropHint && !hasJobs ? (
        <div className="status-dock-drop-target" data-testid="status-dock-drop-target">
          <p className="status-dock-drop-hint" data-testid="status-dock-drop-hint">
            {dropHint}
          </p>
        </div>
      ) : null}
    </div>
  );
}

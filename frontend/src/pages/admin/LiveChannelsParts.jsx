import { liveJobRailCopy } from "../../lib/liveChannelsJob.js";

/** True once the broadcast side is up and at least one channel exists. */
export function isLiveChannelsLaunched(status, engineProgress) {
  const engineUp = Boolean(
    status?.broadcast?.sidecar_up || engineProgress?.ready || engineProgress?.http_ready,
  );
  return engineUp && Number(status?.channel_count ?? 0) > 0;
}

export function LiveStatusCheck({ ok, soft = false, children, testId }) {
  const mark = ok ? "✓" : soft ? "○" : "✗";
  const tone = ok ? "ok" : soft ? "soft" : "fail";
  return (
    <li className={`live-channels-check live-channels-check-${tone}`} data-testid={testId}>
      <span className="live-channels-check-mark" aria-hidden="true">
        {mark}
      </span>
      <span className="live-channels-check-body">{children}</span>
    </li>
  );
}

export function LiveReadyBadge({ ready, label = "Ready", testId }) {
  if (!ready) return null;
  return (
    <span className="certified-badge certified-badge-ok" data-testid={testId}>
      ✓ {label}
    </span>
  );
}

export function LiveJobRail({ job, compact = false }) {
  const copy = liveJobRailCopy(job);
  if (!copy) return null;
  return (
    <div
      className={`live-channels-job-rail${compact ? " is-compact" : ""}`}
      role="status"
      aria-live="polite"
      data-testid={compact ? "live-channels-job-rail-snippet" : "live-channels-job-rail"}
    >
      {copy}
    </div>
  );
}

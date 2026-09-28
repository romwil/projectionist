/** Visible-section job polls. HDMI/kiosk Chromium often skips document.hidden. */

export const BUSY_POLL_MS = 2000;
export const IDLE_POLL_MS = 8000;

export function documentIsHidden(doc = typeof document !== "undefined" ? document : null) {
  return Boolean(doc?.hidden);
}

export function nextPollDelayMs({ busy = false, hidden = false } = {}) {
  if (hidden) return null;
  return busy ? BUSY_POLL_MS : IDLE_POLL_MS;
}

export function shouldPollVisibleSection({ sectionVisible = false, hidden = false } = {}) {
  return Boolean(sectionVisible) && !hidden;
}

export function jobIsActive(job) {
  const status = String(job?.status || "").toLowerCase();
  return status === "running" || status === "queued";
}

export function syncToastIsOpen(jobs = []) {
  return (Array.isArray(jobs) ? jobs : []).some(jobIsActive);
}

export function shouldPollChatJobs({ syncToastOpen = false, hidden = false } = {}) {
  return Boolean(syncToastOpen) && !hidden;
}

export function snapshotIsBusy(snap) {
  return Boolean(snap?.busy);
}

/**
 * Call `tick` immediately, then on a busy/idle delay. Hidden tabs pause.
 * Idle backoff applies even when visibility is unreliable.
 *
 * @returns {() => void} stop
 */
export function startVisibleBusyPoll(tick, options = {}) {
  const {
    isBusy = () => false,
    isHidden = documentIsHidden,
    isEnabled = () => true,
    busyMs = BUSY_POLL_MS,
    idleMs = IDLE_POLL_MS,
    addVisibilityListener = (handler) => {
      if (typeof document === "undefined") return () => {};
      document.addEventListener("visibilitychange", handler);
      return () => document.removeEventListener("visibilitychange", handler);
    },
  } = options;

  let timeoutId = null;
  let stopped = false;
  let inFlight = false;

  function delayMs() {
    if (!isEnabled()) return null;
    const hidden = Boolean(isHidden());
    if (hidden) return null;
    return isBusy() ? busyMs : idleMs;
  }

  async function runTick() {
    if (stopped || !isEnabled() || isHidden() || inFlight) return;
    inFlight = true;
    try {
      await tick();
    } finally {
      inFlight = false;
    }
  }

  function schedule() {
    if (stopped) return;
    if (timeoutId != null) {
      clearTimeout(timeoutId);
      timeoutId = null;
    }
    const ms = delayMs();
    if (ms == null) return;
    timeoutId = setTimeout(async () => {
      timeoutId = null;
      if (stopped) return;
      await runTick();
      schedule();
    }, ms);
  }

  function onVisibility() {
    if (stopped) return;
    if (isHidden() || !isEnabled()) {
      if (timeoutId != null) {
        clearTimeout(timeoutId);
        timeoutId = null;
      }
      return;
    }
    runTick().finally(schedule);
  }

  const removeVisibility = addVisibilityListener(onVisibility);
  runTick().finally(schedule);

  return () => {
    stopped = true;
    if (timeoutId != null) {
      clearTimeout(timeoutId);
      timeoutId = null;
    }
    removeVisibility?.();
  };
}

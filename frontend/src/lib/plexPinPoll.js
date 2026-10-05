/** How often to ask whether the open Plex PIN is linked. Do not hammer plex.tv. */
export const PLEX_PIN_POLL_INTERVAL_MS = 1000;

/**
 * First look is immediate (attempt 0). Later looks wait one interval.
 * A linked PIN must not schedule another look.
 */
export function plexPinPollDelayMs(attempt, intervalMs = PLEX_PIN_POLL_INTERVAL_MS) {
  const n = Number(attempt);
  const interval = Number(intervalMs);
  const wait = Number.isFinite(interval) && interval >= 0 ? interval : PLEX_PIN_POLL_INTERVAL_MS;
  if (!Number.isFinite(n) || n <= 0) return 0;
  return wait;
}

/**
 * True on the first payload that means Plex has linked the PIN.
 * Login needs a household user. Link-Plex peek only needs `authorized`.
 */
export function plexPinPollSucceeded(result, { peek = false } = {}) {
  if (!result || typeof result !== "object") return false;
  if (peek) return result.authorized === true;
  return result.authenticated === true && result.user != null && typeof result.user === "object";
}

/**
 * Poll until Plex links the PIN or the deadline passes.
 * The first check runs immediately. Success calls `onSuccess` once and stops.
 *
 * @returns {() => void} stop
 */
export function startPlexPinPoll({
  poll,
  onSuccess,
  onTimeout,
  onError,
  deadline,
  peek = false,
  intervalMs = PLEX_PIN_POLL_INTERVAL_MS,
  now = () => Date.now(),
  schedule = (fn, ms) => setTimeout(fn, ms),
  clear = (id) => clearTimeout(id),
} = {}) {
  let timer = null;
  let stopped = false;
  let attempt = 0;

  function stop() {
    stopped = true;
    if (timer != null) {
      clear(timer);
      timer = null;
    }
  }

  function arm() {
    if (stopped) return;
    const delay = plexPinPollDelayMs(attempt, intervalMs);
    timer = schedule(() => {
      timer = null;
      void run();
    }, delay);
  }

  async function run() {
    if (stopped) return;
    if (now() >= deadline) {
      stop();
      onTimeout?.();
      return;
    }
    attempt += 1;
    try {
      const result = await poll();
      if (stopped) return;
      if (plexPinPollSucceeded(result, { peek })) {
        stop();
        onSuccess?.(result);
        return;
      }
      if (now() >= deadline) {
        stop();
        onTimeout?.();
        return;
      }
      arm();
    } catch (error) {
      if (stopped) return;
      stop();
      onError?.(error);
    }
  }

  arm();
  return stop;
}

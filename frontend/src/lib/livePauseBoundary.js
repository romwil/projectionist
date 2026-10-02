/**
 * Live pause-past-program-boundary helpers.
 * Projectionist owns the schedule — finishing stretches reality into catch-up.
 */

/**
 * `{ open: false }` is a Rejoin/Finish choice on the current pause.
 * It suppresses the prompt until playback leaves pause or the next pause
 * gesture clears it. An open dialog and a missing boundary are not dismissed.
 * @param {{ open?: boolean } | null | undefined} pauseBoundary
 * @returns {boolean}
 */
export function isPauseBoundaryDismissed(pauseBoundary) {
  return Boolean(pauseBoundary && pauseBoundary.open === false);
}

/**
 * Keep a Rejoin/Finish dismissal while this pause is still active so the
 * dialog does not reopen inside the old boundary. Once playback leaves
 * pause, drop it so a later pause can arm a new program end.
 * An open dialog is left alone.
 * @param {{ open?: boolean } | null | undefined} pauseBoundary
 * @param {string} status
 * @returns {{ open?: boolean } | null | undefined}
 */
export function pauseBoundaryForPlaybackStatus(pauseBoundary, status) {
  if (status !== "paused" && isPauseBoundaryDismissed(pauseBoundary)) return null;
  return pauseBoundary;
}

/**
 * A new pause gesture starts clean. Leftover `{ open: false }` from the
 * previous choice must not suppress the prompt for this pause.
 * @param {{ open?: boolean } | null | undefined} pauseBoundary
 * @returns {{ open?: boolean } | null | undefined}
 */
export function pauseBoundaryOnPauseGesture(pauseBoundary) {
  if (isPauseBoundaryDismissed(pauseBoundary)) return null;
  return pauseBoundary;
}

/**
 * @param {{
 *   paused: boolean,
 *   pauseWallSec?: number|null,
 *   programEndsAtSec?: number|null,
 *   nowSec?: number,
 *   dismissed?: boolean,
 * }} input
 * @returns {boolean}
 */
export function shouldPromptPausePastBoundary(input) {
  if (!input?.paused) return false;
  if (input.dismissed) return false;
  const ends = Number(input.programEndsAtSec);
  if (!Number.isFinite(ends)) return false;
  const now = Number.isFinite(Number(input.nowSec)) ? Number(input.nowSec) : Date.now() / 1000;
  return now >= ends;
}

/**
 * Snapshot program end when the viewer pauses.
 * @param {{ ends_at?: number|null, stop?: number|null, secondsRemaining?: number|null } | null | undefined} osd
 * @param {number} [nowSec]
 * @returns {number|null}
 */
export function programEndSecFromOsd(osd, nowSec = Date.now() / 1000) {
  if (!osd || typeof osd !== "object") return null;
  const end = Number(osd.ends_at ?? osd.stop);
  if (Number.isFinite(end) && end > 0) return end;
  const remaining = Number(osd.secondsRemaining);
  if (Number.isFinite(remaining) && remaining >= 0) {
    return Number(nowSec) + remaining;
  }
  return null;
}

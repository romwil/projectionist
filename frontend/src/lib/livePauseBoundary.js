/**
 * Live pause-past-program-boundary helpers.
 * Projectionist owns the schedule — finishing stretches reality into catch-up.
 */

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

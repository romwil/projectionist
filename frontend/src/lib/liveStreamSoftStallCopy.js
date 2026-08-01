/**
 * Wry / nostalgic living-room lines for soft Live TV buffer stalls.
 * Hard failures stay in formatLiveStreamError — never pull from this list.
 */

/** @type {readonly string[]} */
export const LIVE_SOFT_STALL_PHRASES = Object.freeze([
  "Adjusting the antenna arms…",
  "Twisting the UHF antenna loop…",
  "Moving the aluminum foil on the back of the TV…",
  "Giving the rabbit ears a quarter turn…",
  "Wiggling the coax until the picture settles…",
  "Waiting for the weather to stop arguing with the signal…",
  "Asking the roof antenna to try a little harder…",
  "Smoothing out a wrinkle in the static…",
  "Re-aiming the dish that isn’t actually a dish…",
  "Holding very still so the picture doesn’t freeze again…",
  "Convincing the vertical hold to behave…",
  "Blowing dust off the imaginary converter box…",
  "Counting snowflakes until the station comes back…",
  "Negotiating with the ghosting on channel whatever…",
  "Finding the sweet spot between the lamp and the radiator…",
  "Taping one more bit of foil to the dipole…",
  "Reminding the tuner which century we’re in…",
  "Waiting for the commercial break to find its feet…",
  "Letting the living-room gremlins finish their snack…",
  "Rotating the loop aerial like a tiny weather vane…",
  "Checking whether someone stood in front of the TV…",
  "Giving the set a polite two-second stare…",
  "Coaxing the signal down from the attic…",
  "Straightening the twin-lead that definitely isn’t there…",
]);

let _lastPhraseIndex = -1;

/**
 * Pick a soft-stall phrase, avoiding an immediate repeat when possible.
 *
 * @param {{
 *   rng?: () => number,
 *   phrases?: readonly string[],
 *   exclude?: string,
 *   avoidRepeat?: boolean,
 * }} [options]
 * @returns {string}
 */
export function pickLiveSoftStallPhrase(options = {}) {
  const phrases = Array.isArray(options.phrases) && options.phrases.length
    ? options.phrases
    : LIVE_SOFT_STALL_PHRASES;
  if (!phrases.length) return "";

  const rng = typeof options.rng === "function" ? options.rng : Math.random;
  const avoidRepeat = options.avoidRepeat !== false;
  const exclude = String(options.exclude || "").trim();

  let pool = phrases;
  if (exclude) {
    const without = phrases.filter((p) => p !== exclude);
    if (without.length) pool = without;
  } else if (avoidRepeat && phrases.length > 1 && _lastPhraseIndex >= 0) {
    const without = phrases.filter((_, i) => i !== _lastPhraseIndex);
    if (without.length) pool = without;
  }

  const roll = Number(rng());
  const idx = Math.max(0, Math.min(pool.length - 1, Math.floor((Number.isFinite(roll) ? roll : 0) * pool.length)));
  const phrase = pool[idx] || phrases[0];
  const absolute = phrases.indexOf(phrase);
  if (absolute >= 0) _lastPhraseIndex = absolute;
  return phrase;
}

/** Test helper — reset repeat memory. */
export function resetLiveSoftStallPhraseMemory() {
  _lastPhraseIndex = -1;
}

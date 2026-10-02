/**
 * Adult Swim–style wry lines for Play seek / Live tune interstitials.
 * Soft Live buffer stalls keep using liveStreamSoftStallCopy — this list is
 * for the full-screen static interstitial while waiting for frames.
 */

/** @type {readonly string[]} */
export const TUNING_PHRASES = Object.freeze([
  "adjusting rabbit ears",
  "sending the kids to the attic to move the antenna",
  "tapping into neighbor's cable",
  "rotating the UHF loop like a tiny weather vane",
  "bribing the vertical hold with a polite stare",
  "asking the roof for one more chance",
  "smoothing a wrinkle in the static",
  "finding the sweet spot between the lamp and the radiator",
  "coaxing the signal down from the attic",
  "waiting for the station ID to remember its lines",
  "re-aiming the dish that isn’t actually a dish",
  "taping one more square of foil to the dipole",
  "negotiating with channel whatever",
  "counting snowflakes until the picture settles",
  "reminding the tuner which century we’re in",
  "holding very still so the ghosting behaves",
  "wiggling the coax until something wiggles back",
  "borrowing a little clarity from next door",
  "warming up the imaginary converter box",
  "asking the living-room gremlins to finish their snack",
]);

let _lastPhraseIndex = -1;

/**
 * Pick a tuning phrase, avoiding an immediate repeat when possible.
 *
 * @param {{
 *   rng?: () => number,
 *   phrases?: readonly string[],
 *   exclude?: string,
 *   avoidRepeat?: boolean,
 * }} [options]
 * @returns {string}
 */
export function pickTuningPhrase(options = {}) {
  const phrases = Array.isArray(options.phrases) && options.phrases.length
    ? options.phrases
    : TUNING_PHRASES;
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
export function resetTuningPhraseMemory() {
  _lastPhraseIndex = -1;
}

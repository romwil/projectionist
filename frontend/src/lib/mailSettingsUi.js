/** Pure copy/helpers for Admin → Mail & alerts. */

/**
 * Field label that notes a secret is already stored.
 * @param {string} label
 * @param {boolean} isSet
 * @returns {string}
 */
export function savedSecretLabel(label, isSet) {
  return isSet ? `${label} (saved — leave blank to keep)` : label;
}

/**
 * Apprise URLs field label with saved count when present.
 * @param {{ urls_set?: boolean, url_count?: number|string }} apprise
 * @returns {string}
 */
export function appriseUrlsLabel(apprise = {}) {
  if (!apprise.urls_set) return "Apprise URLs";
  const count = apprise.url_count || "saved";
  return `Apprise URLs (${count} saved — leave blank to keep)`;
}

/**
 * Short success line after Apprise test.
 * @param {{ notified?: number }} result
 * @returns {string}
 */
export function appriseTestResultMessage(result = {}) {
  const n = Number(result.notified) || 0;
  return `Apprise test notified ${n} destination${n === 1 ? "" : "s"}.`;
}

/**
 * Short success line after mail test.
 * @param {{ to_email?: string }} result
 * @returns {string}
 */
export function mailTestResultMessage(result = {}) {
  const to = result.to_email || "your notification address";
  return `Test email sent to ${to}.`;
}

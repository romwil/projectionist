/**
 * Secret fields on Admin Connections / setup.
 *
 * GET /api/settings never returns plaintext secrets (`_mask_settings` clears them and
 * sets `{field}_set` / `{field}_source`). Show/Hide can reveal:
 *   1. a draft the user typed in this session, or
 *   2. a stored secret fetched via owner-only POST /api/settings/secrets/reveal.
 */

/** Placeholder when a secret is already saved (or set via env). */
export function secretPlaceholder(settings, field, fallback = "") {
  if (settings?.[`${field}_source`] === "env") {
    return "Set by the host environment";
  }
  if (settings?.[`${field}_set`]) {
    return "Configured (leave blank to keep)";
  }
  return fallback;
}

/** Seerr nests `api_key_set` under `settings.seerr`. */
export function seerrSecretPlaceholder(settings, fallback = "") {
  if (settings?.seerr?.api_key_set) {
    return "Configured (leave blank to keep)";
  }
  return fallback;
}

/** Whether settings report a saved (but redacted) secret for this field. */
export function isSecretConfigured(settings, field) {
  if (field === "seerr.api_key") {
    return Boolean(settings?.seerr?.api_key_set);
  }
  return Boolean(settings?.[`${field}_set`]);
}

/**
 * Show/Hide when there is a draft value, or when a stored secret can be fetched.
 * Empty + not configured → no toggle (nothing to reveal).
 */
export function canToggleSecretVisibility(value, { configured = false } = {}) {
  return String(value ?? "").length > 0 || Boolean(configured);
}

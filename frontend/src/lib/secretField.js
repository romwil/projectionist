/**
 * Secret fields on Admin Connections / setup.
 *
 * GET /api/settings never returns plaintext secrets (`_mask_settings` clears them and
 * sets `{field}_set` / `{field}_source`). Show/Hide can only reveal a draft the user
 * typed in this session — never the stored value.
 */

/** Placeholder when a secret is already saved (or set via env). */
export function secretPlaceholder(settings, field, fallback = "") {
  if (settings?.[`${field}_source`] === "env") {
    return "Configured via environment (.env)";
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

/**
 * Show/Hide is only honest when there is a non-empty draft value in the input.
 * An empty field with a "configured" placeholder has nothing to reveal.
 */
export function canToggleSecretVisibility(value) {
  return String(value ?? "").length > 0;
}

import type {JsonObject, JsParam} from "../api/types";
/** Pure helpers for the multi-user login screen layout and copy. */

export const AUTH_METHOD_ORDER = ["plex", "oidc", "local"];

/**
 * Stable display order for enabled auth methods.
 * Plex is first — the household front door — then SSO, then local password.
 *
 * @param {Iterable<string> | null | undefined} authMethods
 * @returns {string[]}
 */
export function resolveAuthMethods(authMethods: JsParam) {
  const enabled = new Set(
    Array.from(authMethods || [])
      .map((method) => String(method || "").trim().toLowerCase())
      .filter(Boolean),
  );
  return AUTH_METHOD_ORDER.filter((method) => enabled.has(method));
}

/**
 * Member-facing lede under the Sign in heading.
 *
 * @param {Iterable<string> | null | undefined} authMethods
 * @returns {string}
 */
export function loginLede(authMethods: JsParam) {
  const methods = resolveAuthMethods(authMethods);
  if (methods.length === 1 && methods[0] === "plex") {
    return "Sign in with your Plex account to open your conversations and watchlist.";
  }
  if (methods.includes("plex")) {
    return "Sign in to open your conversations and watchlist. Most households use Plex.";
  }
  return "Sign in to open your conversations and watchlist.";
}

/**
 * Copy + control labels for the tucked-away Plex token recovery path.
 *
 * @param {{ open?: boolean }} [options]
 */
export function plexAdvancedCopy(options: JsParam = {}) {
  const open = Boolean(options.open);
  return {
    toggleLabel: open ? "Hide advanced" : "Advanced",
    tokenLabel: "Plex token",
    tokenPlaceholder: "Paste token",
    tokenHelp: "Recovery only — prefer Sign in with Plex above.",
    submitLabel: "Continue with token",
    emptyError: "Paste a Plex token to continue.",
  };
}

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
 * One-line statement of what this product is (PRD-004). A member landing on
 * a custom household domain has no guarantee the "Projectionist" brand name
 * ever appeared, so the door states the product plainly before asking them
 * to sign in.
 */
export const LOGIN_PRODUCT_STATEMENT =
  "Projectionist is your household's private movie and TV companion — chat for recommendations, browse the library, and watch together.";

/**
 * Member-facing lede under the Sign in heading.
 *
 * @param {Iterable<string> | null | undefined} authMethods
 * @returns {string}
 */
export function loginLede(authMethods: JsParam) {
  const methods = resolveAuthMethods(authMethods);
  const action = (() => {
    if (methods.length === 1 && methods[0] === "plex") {
      return "Sign in with your Plex account to open your conversations and watchlist.";
    }
    if (methods.includes("plex")) {
      return "Sign in to open your conversations and watchlist. Most households use Plex.";
    }
    return "Sign in to open your conversations and watchlist.";
  })();
  return `${LOGIN_PRODUCT_STATEMENT} ${action}`;
}

/**
 * UX-011: what /login does once features and the session are known.
 * A signed-in person never sees the sign-in form; they go to their page.
 *
 * - `setup`    — first-run install, send to /setup
 * - `redirect` — single-owner mode or an existing session, leave the door
 * - `form`     — signed out in household mode, show sign-in
 */
export function loginDoorDecision({
  features,
  me,
}: { features?: JsonObject | null; me?: JsonObject | null } = {}): "setup" | "redirect" | "form" {
  if (features?.setup_state === "setup") return "setup";
  if (!features?.features?.multi_user_enabled) return "redirect";
  if (me?.user) return "redirect";
  return "form";
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

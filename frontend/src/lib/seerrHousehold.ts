import type {JsonObject, JsParam} from "../api/types";
/**
 * Admin Household → Sync Seerr confirm copy (replaces window.prompt).
 */
export function seerrSyncConfirmOptions(displayName: JsParam) {
  const who = String(displayName || "").trim() || "this user";
  return {
    title: "Sync Seerr account",
    body: `Paste a Plex auth token for ${who} to link their Seerr account.`,
    confirmLabel: "Sync",
    prompt: {
      label: "Plex auth token",
      placeholder: "Plex token",
      type: "password",
    },
  };
}

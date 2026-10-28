import type {JsonObject, JsParam} from "../api/types";
/**
 * Severity for Tunarr start timeout feedback.
 * InlineAlert only renders success|error; still-starting (container up, HTTP
 * not ready) is a soft notice matching ok:true — not a failure.
 */
export function liveChannelsStartTimeoutAlertType(stillStarting: JsParam) {
  return stillStarting ? "success" : "error";
}

/**
 * Severity for Tunarr start timeout feedback.
 * InlineAlert only renders success|error; still-starting (container up, HTTP
 * not ready) is a soft notice matching ok:true — not a failure.
 */
export function liveChannelsStartTimeoutAlertType(stillStarting) {
  return stillStarting ? "success" : "error";
}

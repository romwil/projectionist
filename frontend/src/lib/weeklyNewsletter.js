/** Pure helpers for owner weekly-newsletter generate UI. */

export const NEWSLETTER_SCOPES = [
  { value: "self", label: "Just me" },
  { value: "users", label: "Selected members" },
  { value: "all", label: "Everyone opted in" },
];

/**
 * @param {"self"|"users"|"all"} scope
 * @param {number} selectedCount
 * @returns {string}
 */
export function newsletterConfirmMessage(scope, selectedCount = 0) {
  if (scope === "self") {
    return "Send this week’s newsletter to your inbox (and email if you’ve enabled it)? You must be opted in under Settings → Notifications.";
  }
  if (scope === "users") {
    const n = Number(selectedCount) || 0;
    const who = n === 1 ? "1 selected member" : `${n} selected members`;
    return `Send this week’s newsletter to ${who}? Only people who opted in will receive it.`;
  }
  return "Send this week’s newsletter to everyone who opted in? Channel prefs (inbox / email) still apply.";
}

/**
 * @param {{ delivered?: number, emailed?: number, skipped_opt_out?: number, targeted?: number }} result
 * @returns {string}
 */
export function newsletterResultMessage(result = {}) {
  const delivered = Number(result.delivered) || 0;
  const emailed = Number(result.emailed) || 0;
  const skipped = Number(result.skipped_opt_out) || 0;
  const parts = [`Delivered to ${delivered} inbox${delivered === 1 ? "" : "es"}`];
  if (emailed > 0) parts.push(`${emailed} emailed`);
  if (skipped > 0) parts.push(`${skipped} skipped (not opted in)`);
  return `${parts.join(" · ")}.`;
}

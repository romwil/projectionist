import type {JsonObject, JsParam} from "../api/types";
/**
 * Resolve how to address the logged-in user in review/rate copy.
 * Never use the curator/agent name here — that belongs in persona prompts.
 */
export function resolveReviewAddressName(user: JsParam) {
  const preferred = String(user?.preferred_name || "").trim();
  if (preferred) return preferred;
  const display = String(user?.display_name || "").trim();
  if (display) return display;
  return null;
}

/** Merge auth/profile sources; never fall back to curator/agent name. */
export function resolveReviewUser(...sources: JsParam) {
  for (const user of sources) {
    const name = resolveReviewAddressName(user);
    if (name) return name;
  }
  return null;
}

export function formatRateBatchLead(userName: JsParam) {
  const name = String(userName || "").trim();
  if (name) {
    return `${name} — tap stars on anything you've watched (half-stars welcome):`;
  }
  return "Rate what you've watched (half-stars welcome):";
}

export function formatRateTitleLead(userName: JsParam, title: string) {
  const name = String(userName || "").trim();
  const label = String(title || "this title").trim() || "this title";
  if (name) {
    return `${name} — quick take on **${label}**?`;
  }
  return `Quick take on **${label}**?`;
}

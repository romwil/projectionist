import type { JsParam } from "../api/types";
import { WARM_EXPLORE_TASKS, isTaskRunning } from "./scheduledTasks.js";

/** Owner ops helpers: Tasks catch-up shortlist, Needs attention, secrets card, audit labels. */

export const CATCHUP_SHORTLIST_LIMIT = 10;
export const TASK_VIEWS = Object.freeze({ catchup: "catchup", all: "all" });

function catchupRank(task: JsParam) {
  if (isTaskRunning(task)) return 0;
  const status = String(task?.last_status || "");
  if (task?.quarantine?.is_quarantined || status.startsWith("error")) return 1;
  if (WARM_EXPLORE_TASKS.includes(task?.name)) return 2;
  if (task?.overdue) return 3;
  if (status === "skipped" && String(task?.last_outcome_reason || "").trim()) return 4;
  return null;
}

/**
 * Monday catch-up: running, failed, or quarantined tasks, then Warm Explore,
 * then overdue and fixable skips. Disabled tasks stay under All tasks.
 * Keeps the caller's order inside each rank.
 */
export function taskCatchupShortlist(items: JsParam, { limit = CATCHUP_SHORTLIST_LIMIT }: JsParam = {}) {
  const list = Array.isArray(items) ? items : [];
  const ranked: Array<{ task: JsParam; rank: number; index: number }> = [];
  list.forEach((task, index) => {
    if (!task?.enabled && !isTaskRunning(task)) return;
    const rank = catchupRank(task);
    if (rank == null) return;
    ranked.push({ task, rank, index });
  });
  ranked.sort((a, b) => a.rank - b.rank || a.index - b.index);
  return ranked.slice(0, Math.max(0, Number(limit) || 0)).map((entry) => entry.task);
}

/** Resolve `?view=` on Tasks. Catch-up is the default. */
export function resolveTaskView(raw: unknown) {
  return String(raw || "").trim().toLowerCase() === TASK_VIEWS.all ? TASK_VIEWS.all : TASK_VIEWS.catchup;
}

const SEVERITY_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };

/** Order Needs attention rows (high first) and summarize for the heading. */
export function summarizeNeedsAttention(items: JsParam) {
  const list = (Array.isArray(items) ? items : [])
    .filter((item) => item && item.id && item.title)
    .slice()
    .sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9));
  const high = list.filter((item) => item.severity === "high").length;
  const tone = high ? "error" : list.length ? "warn" : "good";
  const headline = list.length
    ? `${list.length} thing${list.length === 1 ? "" : "s"} need${list.length === 1 ? "s" : ""} attention`
    : "Nothing needs attention";
  return { items: list, count: list.length, high, tone, headline };
}

const SECRET_STATE_COPY: Record<string, { label: string; tone: string }> = {
  connected: { label: "Connected", tone: "good" },
  needs_key: { label: "Key can't be read", tone: "error" },
  stale: { label: "Marked connected, no key", tone: "warn" },
  untested: { label: "Key saved, not tested", tone: "warn" },
  off: { label: "Not set up", tone: "neutral" },
};

export function secretStateCopy(state: unknown) {
  return SECRET_STATE_COPY[String(state || "")] || SECRET_STATE_COPY.off;
}

/** Last Test time for a service row. Certification rows store UTC `YYYY-MM-DD HH:MM:SS`. */
export function formatLastProbe(value: unknown) {
  const text = String(value || "").trim();
  if (!text) return "Never tested";
  const iso = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(text) ? `${text.replace(" ", "T")}Z` : text;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return `Tested ${text}`;
  return `Tested ${date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}`;
}

export function checklistProgress(items: JsParam) {
  const list = Array.isArray(items) ? items : [];
  const done = list.filter((item) => item?.status === "done").length;
  const skipped = list.filter((item) => item?.status === "skipped").length;
  return { done, skipped, total: list.length, open: list.length - done - skipped };
}

const AUDIT_EVENT_LABELS: Record<string, string> = {
  sign_in: "Signed in",
  sign_in_failed: "Sign-in refused",
  sign_out_everywhere: "Signed out everywhere",
  password_change: "Changed password",
  password_reset: "Password reset by owner",
  invite_create: "Invite created",
  invite_revoke: "Invite revoked",
  invite_redeem: "Joined with an invite",
  access_request_approve: "Access request approved",
  access_request_deny: "Access request denied",
  account_create: "Account created",
  role_change: "Role changed",
  account_disable: "Account enabled or disabled",
  youth_change: "Youth setting changed",
  account_delete: "Account removed",
  settings_save: "Settings saved",
  secret_reveal: "Saved key shown",
  mcp_key_rotate: "MCP key rotated",
  mcp_key_clear: "MCP key cleared",
  household_backup: "Household backup downloaded",
};

export function auditEventLabel(event: unknown) {
  const key = String(event || "");
  return AUDIT_EVENT_LABELS[key] || key.replace(/_/g, " ");
}

/** One plain line for an audit row's detail. Field names only; rows never carry values. */
export function auditDetailLine(row: JsParam) {
  const detail = row?.detail && typeof row.detail === "object" ? row.detail : {};
  const parts: string[] = [];
  if (detail.method) parts.push(`via ${detail.method}`);
  if (detail.before && detail.after) parts.push(`${detail.before} → ${detail.after}`);
  if (typeof detail.is_youth === "boolean") parts.push(detail.is_youth ? "youth on" : "youth off");
  if (typeof detail.disabled === "boolean") parts.push(detail.disabled ? "disabled" : "enabled");
  if (detail.role && !detail.after) parts.push(`role ${detail.role}`);
  if (detail.field) parts.push(String(detail.field));
  if (detail.which) parts.push(`${detail.which} key`);
  if (Array.isArray(detail.fields) && detail.fields.length) {
    const shown = detail.fields.slice(0, 4).join(", ");
    const more = detail.fields.length > 4 ? ` +${detail.fields.length - 4} more` : "";
    parts.push(`${shown}${more}`);
  }
  if (detail.username) parts.push(`as “${detail.username}”`);
  return parts.join(" · ");
}

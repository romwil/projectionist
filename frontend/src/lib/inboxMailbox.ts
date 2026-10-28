/**
 * Mailbox rules for /inbox.
 * Read keeps a row. Dismiss (seen_at) removes it. Agent notes reply in place.
 */

import { digestPicks, isEnthusiastNudge } from "./recommendationInbox.js";
import type {JsonObject, LibraryItem, JsParam} from "../api/types";

export const INBOX_PAGE_SIZE = 12;

export const INBOX_NOTE_PREFIX = "[inbox-note]\n";
export const INBOX_REPLY_MARK = "\n\n[reply]\n";

const KIND_LABELS: Record<string, any> = {
  recommendation: "Recommendations",
  arrival: "Arrivals",
  "access-request": "Access requests",
  digest: "Notes",
  nudge: "Curator notes",
  "library-share": "Shared pages",
  "year-in-review": "Year in Review",
};

export function inboxKindLabel(kind: string) {
  return KIND_LABELS[kind] || kind || "Other";
}

/**
 * One modest page. Default status is every note that has not been dismissed,
 * so marking a row read does not take it off the list.
 */
export function inboxListParams({ status = "all", sort = "newest", kind = "", page = 0 }: JsParam = {}) {
  const params: JsParam = {
    status: status === "unread" || status === "read" ? status : "all",
    sort: sort === "oldest" ? "oldest" : "newest",
    limit: INBOX_PAGE_SIZE,
    offset: Math.max(0, Number(page) || 0) * INBOX_PAGE_SIZE,
  };
  if (kind) params.kind = kind;
  return params;
}

/** Scan line: a finished sentence, or a word boundary when the sentence is long. */
export function inboxScanPreview(text: string, { maxLen = 220 }: JsParam = {}) {
  const raw = String(text || "").replace(/\s+/g, " ").trim();
  if (!raw) return { text: "", continues: false };
  const match = raw.match(/^(.+?[.!?])(?:\s|$)/);
  const sentence = (match ? match[1] : raw).trim();
  const continues = sentence.length < raw.length;
  if (sentence.length <= maxLen) return { text: sentence, continues };
  const slice = sentence.slice(0, maxLen);
  const space = slice.lastIndexOf(" ");
  const cut = (space > 40 ? slice.slice(0, space) : slice).trim();
  return { text: `${cut}…`, continues: true };
}

function enthusiastBody(item: LibraryItem | null | undefined) {
  const why = String(item?.payload?.pick_why || "").trim();
  if (why) return why;
  return String(item?.body || item?.message || "")
    .split(/\n+/)
    .map((line) => line.trim())
    .filter((line) => line && !/recently watched/i.test(line))
    .join("\n")
    .trim();
}

export function inboxSubjectTitles(item: LibraryItem | null | undefined) {
  const picks = digestPicks(item, { limit: 24 });
  if (picks.length) return picks.map((pick) => (pick as JsParam).title);
  const media = String(item?.payload?.title || item?.media_title || "").trim();
  if (media) return [media];
  return [];
}

/** Full stored note. Does not invent recommendation copy. */
export function inboxFullMessage(item: LibraryItem | null | undefined) {
  const body = isEnthusiastNudge(item)
    ? enthusiastBody(item)
    : String(item?.body || item?.message || "").trim();
  return {
    title: String(item?.title || "Note").trim() || "Note",
    body,
    when: item?.created_at ?? null,
    titles: inboxSubjectTitles(item),
  };
}

export function formatInboxWhen(createdAt: JsParam) {
  const value = Number(createdAt);
  if (!Number.isFinite(value) || value <= 0) return "";
  const ms = value < 1e12 ? value * 1000 : value;
  const date = new Date(ms);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function applyInboxRead(items: LibraryItem[] | null | undefined, id: string, readAt: JsParam) {
  return (items || []).map((item) => (item.id === id ? { ...item, read_at: readAt } : item));
}

export function applyInboxDismiss(items: LibraryItem[] | null | undefined, ids: JsParam) {
  const drop = new Set(ids || []);
  return (items || []).filter((item) => !drop.has(item.id));
}

export function inboxPageSelection(items: LibraryItem[] | null | undefined, selected: JsParam) {
  const ids = (items || []).map((item) => item.id).filter(Boolean);
  const chosen = selected instanceof Set ? selected : new Set(selected || []);
  return {
    ids,
    all: ids.length > 0 && ids.every((id) => chosen.has(id)),
  };
}

/**
 * Weekly notes, house letters, and other curator messages.
 * A "Worth a look" title card is a recommendation, not a conversation.
 */
export function isAgentInboxNote(item: LibraryItem | null | undefined) {
  if (!item || isEnthusiastNudge(item)) return false;
  const kind = String(item.kind || "");
  return kind === "digest" || kind === "nudge" || kind === "year-in-review";
}

export function defaultInboxPersona(personas: JsParam) {
  const list = Array.isArray(personas)
    ? personas
    : personas?.items || personas?.personas || [];
  return list.find((persona: JsParam) => persona?.is_default) || list[0] || null;
}

/** First turn carries the stored note. Later turns are the typed reply. */
export function inboxAgentOutboundMessage(noteBody: unknown, reply: unknown, { first = false }: JsParam = {}) {
  const typed = String(reply || "").trim();
  if (!first) return typed;
  return `${INBOX_NOTE_PREFIX}${String(noteBody || "").trim()}${INBOX_REPLY_MARK}${typed}`;
}

/** Hide the note prefix so the thread shows the person's reply, not a duplicate note. */
export function visibleInboxReply(text: string) {
  const raw = String(text || "");
  const mark = raw.lastIndexOf("[reply]\n");
  if (mark >= 0) return raw.slice(mark + "[reply]\n".length).trim();
  if (raw.startsWith("[inbox-note]")) return "";
  return raw.trim();
}

export function inboxReplyText(message: JsParam) {
  const blocks = Array.isArray(message?.blocks) ? message.blocks : [];
  const joined = blocks
    .map((block: JsParam) => String(block?.content || block?.text || ""))
    .filter(Boolean)
    .join("\n");
  const raw = joined || String(message?.content || message?.text || "");
  if (message?.role === "assistant") return raw.trim();
  return visibleInboxReply(raw);
}

/** A reply stays on this note. It does not open the main chat route. */
export function inboxReplySubmission() {
  return { stayOnInbox: true, route: null };
}

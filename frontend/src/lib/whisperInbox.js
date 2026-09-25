/** Pure helpers for the named-member whisper inbox. */

export const WHY_WORD_LIMIT = 12;
export const WHISPER_PATH = "/whisper";

const FORBIDDEN = ["download complete", "grabbed", "nzb", "torrent complete"];

export function clipWhy(text, { limit = WHY_WORD_LIMIT } = {}) {
  const words = String(text || "")
    .split(/\s+/)
    .filter(Boolean);
  if (!words.length) return "";
  return words.slice(0, Math.max(1, Number(limit) || WHY_WORD_LIMIT)).join(" ");
}

export function whyWordCount(text) {
  return String(text || "")
    .split(/\s+/)
    .filter(Boolean).length;
}

export function isForbiddenWhisperCopy(text) {
  const lowered = String(text || "").toLowerCase();
  return FORBIDDEN.some((banned) => lowered.includes(banned));
}

export function whisperWhy(item) {
  const raw = item?.why || item?.payload?.why || item?.body || item?.message || "";
  return clipWhy(raw);
}

export function whisperMemberName(item, fallback = "You") {
  const fromItem = String(item?.member_name || item?.payload?.member_name || "").trim();
  if (fromItem) return fromItem;
  return String(fallback || "You").trim() || "You";
}

export function isWhisperItem(item) {
  if (!item) return false;
  if (String(item.kind || "") === "whisper") return true;
  return Boolean(item?.payload?.whisper);
}

export function whisperInboxHeadline({ memberName, count } = {}) {
  const name = String(memberName || "").trim();
  const n = Number(count) || 0;
  if (name && n > 1) return `${n} whispers for ${name}`;
  if (name) return `A whisper for ${name}`;
  return n > 1 ? `${n} whispers` : "Whispers";
}

export function whisperHomeLabel({ memberName, unreadCount } = {}) {
  const unread = Number(unreadCount) || 0;
  const name = String(memberName || "").trim();
  if (unread > 0 && name) return `A whisper for ${name}`;
  if (unread > 0) return "A whisper for you";
  return "Whispers";
}

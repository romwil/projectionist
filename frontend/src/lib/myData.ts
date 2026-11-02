/** Settings → My data (PRIV-023): helpers shared by the page and its unit test. */

/** Must match ERASE_CONFIRM_PHRASE in projectionist/web/auth_routes.py. */
export const ERASE_CONFIRM_PHRASE = "delete my data";

export type ExportFormat = "json" | "markdown";

export function exportMyDataUrl(format: ExportFormat): string {
  return `/api/me/memory?format=${format}`;
}

export function erasePhraseMatches(value: string): boolean {
  return value.trim().toLowerCase() === ERASE_CONFIRM_PHRASE;
}

export type MemoryNote = {
  id: string;
  kind?: string;
  text?: string;
  updated_at?: number;
};

const NOTE_KIND_LABELS: Record<string, string> = {
  preference: "Preference",
  self_disclosure: "About you",
  learning_goal: "Goal",
  watch_intention: "Plans to watch",
  follow_up: "Follow-up",
};

export function noteKindLabel(kind?: string): string {
  if (!kind) return "Note";
  return NOTE_KIND_LABELS[kind] || kind.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export function erasedSummary(total: number): string {
  if (total <= 0) return "There was nothing to delete.";
  return `Deleted ${total.toLocaleString()} ${total === 1 ? "item" : "items"}. Your account is still here.`;
}

import type {JsonObject, JsParam} from "../api/types";
const DEFINITION_RE = /^\[\^([^\]]+)\]:\s*(.+)$/gm;
const HREF_ID_RE = /(?:user-content-)?fn(?:ref)?-([A-Za-z0-9_-]+)/i;
const WALK_ID_RE = /^(lineage|canon|map|compare|seminar|gap)-(.+)$/i;

export const WALK_SHEET_LABELS: Record<string, any> = {
  lineage: "Lineage",
  canon: "Canon",
  map: "Map",
  compare: "Compare",
  seminar: "Seminar",
  gap: "Gap list",
};

export function footnoteWalkKind(id: string) {
  const match = String(id || "").trim().match(WALK_ID_RE);
  return match ? match[1].toLowerCase() : "";
}

export function footnoteSheetLabel(note: JsParam) {
  const id = String(note?.id ?? note ?? "").trim();
  const match = id.match(WALK_ID_RE);
  if (match) {
    const kind = match[1].toLowerCase();
    const suffix = match[2];
    const label = WALK_SHEET_LABELS[kind] || "Walk";
    return `${label} source ${suffix}`;
  }
  return id ? `Source ${id}` : "Source";
}

export function parseMarkdownFootnotes(markdown: JsParam) {
  const notes: JsParam[] = [];
  const seen = new Set();
  const text = String(markdown || "");
  DEFINITION_RE.lastIndex = 0;
  let match;
  while ((match = DEFINITION_RE.exec(text))) {
    const id = String(match[1] || "").trim();
    const body = String(match[2] || "").trim();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    notes.push({ id, text: body });
  }
  return notes;
}

export function footnoteIdFromHref(href: string, fallback: string = "") {
  const raw = String(href || "");
  const match = raw.match(HREF_ID_RE);
  if (match?.[1]) return match[1];
  return String(fallback || "").trim();
}

export function findFootnote(notes: JsParam, id: string) {
  const key = String(id || "").trim();
  if (!key) return null;
  return notes.find((note: JsParam) => String(note.id) === key) || null;
}

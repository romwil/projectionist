const DEFINITION_RE = /^\[\^([^\]]+)\]:\s*(.+)$/gm;
const HREF_ID_RE = /(?:user-content-)?fn(?:ref)?-([A-Za-z0-9_-]+)/i;

export function parseMarkdownFootnotes(markdown) {
  const notes = [];
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

export function footnoteIdFromHref(href, fallback = "") {
  const raw = String(href || "");
  const match = raw.match(HREF_ID_RE);
  if (match?.[1]) return match[1];
  return String(fallback || "").trim();
}

export function findFootnote(notes, id) {
  const key = String(id || "").trim();
  if (!key) return null;
  return notes.find((note) => String(note.id) === key) || null;
}

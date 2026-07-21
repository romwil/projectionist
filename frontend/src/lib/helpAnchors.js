/**
 * Anchor-id helpers for the in-app Help page.
 *
 * Headings in docs/HELP.md are rendered by react-markdown; to make every
 * section deep-linkable we derive a stable, GitHub-compatible slug from the
 * heading text. The slug algorithm matches GitHub's so existing anchors used
 * across the app (e.g. `#coverage-over-time`, `#for-owners--curation--scheduler`)
 * keep resolving without a hand-maintained lookup table.
 */

/**
 * Convert heading text to a GitHub-style anchor slug.
 * - lowercased
 * - punctuation removed (spaces around removed punctuation collapse to hyphens,
 *   preserving the double-hyphens GitHub produces for em dashes / ampersands)
 * - each whitespace character becomes a hyphen
 */
export function slugify(text) {
  return String(text ?? "")
    .trim()
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/\s/g, "-");
}

/**
 * Decode a `location.hash` into the target element id to scroll to.
 * Returns "" when there is no usable anchor.
 */
export function targetIdFromHash(hash) {
  const raw = String(hash ?? "").replace(/^#/, "").trim();
  if (!raw) return "";
  try {
    return decodeURIComponent(raw).trim();
  } catch {
    return raw;
  }
}

/**
 * Build a stateful slugger that de-duplicates repeated slugs by appending
 * `-1`, `-2`, … (GitHub's behavior). Create one per rendered document.
 */
export function createSlugger() {
  const seen = new Map();
  return function slug(text) {
    const base = slugify(text);
    if (!base) return base;
    const count = seen.get(base) || 0;
    seen.set(base, count + 1);
    return count === 0 ? base : `${base}-${count}`;
  };
}

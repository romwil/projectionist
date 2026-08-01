/**
 * Normalize the stored `content.blocks` of a saved library page into an ordered
 * list of inert render descriptors.
 *
 * Saved pages at `/library/:id` are static snapshots: they must render every
 * block in order — intro text, title cards, an inert preview of any
 * recommendation viewport, and suggested replies — and must NEVER trigger an
 * interactive takeover (e.g. auto-opening the turnstyle/viewport overlay).
 *
 * Design notes:
 * - `action_prompt` / `open_viewport` blocks describe an interactive turnstyle
 *   view in live chat. On a saved page we render their items as an inert card
 *   grid instead, and only when a sibling `title_cards` block is NOT already
 *   showing the same recommendations (avoids a duplicate grid).
 * - Unknown or empty blocks are skipped rather than rendered as blank text
 *   nodes (the previous catch-all rendered them through MessageText, which
 *   produced empty markdown and dropped non-text payloads).
 * - Title rails are hardened: de-dupe by tmdb/tvdb id, drop cards without a
 *   usable identity, and cap length so a bad gap-save cannot blow up the page.
 *
 * @param {Array<object>} blocks
 * @returns {Array<{kind: string, [key: string]: unknown}>}
 */

/** Max posters shown per rail on a saved library page. */
export const SAVED_LIBRARY_RAIL_LIMIT = 12;

/**
 * De-dupe and bound title cards for saved-library rails.
 * Fail closed on missing title or missing tmdb/tvdb id (invented gap junk).
 *
 * @param {Array<object>} items
 * @param {{ limit?: number }} [opts]
 * @returns {Array<object>}
 */
export function sanitizeSavedRailItems(items = [], opts = {}) {
  const limit = Math.max(1, Number(opts.limit) || SAVED_LIBRARY_RAIL_LIMIT);
  const list = Array.isArray(items) ? items : [];
  const kept = [];
  const seen = new Set();

  for (const raw of list) {
    if (!raw || typeof raw !== "object") continue;
    const title = String(raw.title || "").trim();
    if (!title) continue;

    const tmdbId = Number(raw.tmdb_id) || 0;
    const tvdbId = Number(raw.tvdb_id) || 0;
    if (tmdbId <= 0 && tvdbId <= 0) continue;

    const mediaType = String(raw.media_type || "").trim().toLowerCase() || "movie";
    const key =
      tmdbId > 0
        ? `${mediaType}:tmdb:${tmdbId}`
        : `${mediaType}:tvdb:${tvdbId}`;
    if (seen.has(key)) continue;
    seen.add(key);
    kept.push(raw);
    if (kept.length >= limit) break;
  }
  return kept;
}

export function savedLibraryBlocks(blocks = []) {
  const list = Array.isArray(blocks) ? blocks : [];
  const hasTitleCards = list.some(
    (block) =>
      block &&
      block.type === "title_cards" &&
      Array.isArray(block.items) &&
      sanitizeSavedRailItems(block.items).length > 0,
  );

  const result = [];
  for (const block of list) {
    if (!block || typeof block !== "object") continue;

    if (block.type === "text" || block.type === "error") {
      const content = typeof block.content === "string" ? block.content : "";
      if (content.trim()) result.push({ kind: "text", content });
      continue;
    }

    if (block.type === "title_cards") {
      const items = sanitizeSavedRailItems(block.items);
      if (items.length) result.push({ kind: "title_cards", items });
      continue;
    }

    if (block.type === "action_prompt" && block.action === "open_viewport") {
      // Inert on a saved page — never auto-opens the viewport. Skip when a
      // title_cards block already renders the same recommendations.
      if (hasTitleCards) continue;
      const items = sanitizeSavedRailItems(block.payload?.items);
      if (items.length) {
        result.push({
          kind: "recommendations",
          title: block.payload?.title || "Recommendations",
          items,
        });
      }
      continue;
    }

    if (block.type === "suggested_replies") {
      const replies = Array.isArray(block.payload?.replies)
        ? block.payload.replies.filter(Boolean).slice(0, 4)
        : [];
      if (replies.length) result.push({ kind: "suggested_replies", replies });
      continue;
    }

    if (block.type === "persona_consult" && block.payload?.answer) {
      result.push({
        kind: "persona_consult",
        persona: block.payload.persona || "Curator",
        lead: block.payload.lead || "",
        answer: String(block.payload.answer),
        specialty: block.payload.specialty || "",
      });
      continue;
    }
  }

  return result;
}

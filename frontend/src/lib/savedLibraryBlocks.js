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
 *
 * @param {Array<object>} blocks
 * @returns {Array<{kind: string, [key: string]: unknown}>}
 */
export function savedLibraryBlocks(blocks = []) {
  const list = Array.isArray(blocks) ? blocks : [];
  const hasTitleCards = list.some(
    (block) =>
      block &&
      block.type === "title_cards" &&
      Array.isArray(block.items) &&
      block.items.length > 0,
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
      const items = Array.isArray(block.items) ? block.items : [];
      if (items.length) result.push({ kind: "title_cards", items });
      continue;
    }

    if (block.type === "action_prompt" && block.action === "open_viewport") {
      // Inert on a saved page — never auto-opens the viewport. Skip when a
      // title_cards block already renders the same recommendations.
      if (hasTitleCards) continue;
      const items = Array.isArray(block.payload?.items) ? block.payload.items : [];
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
  }

  return result;
}

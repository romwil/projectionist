/** Pure helpers for collections/courses ordering and authoring. */

/** Sort course/collection items by position, then created_at, stably. */
export function orderCollectionSteps(items) {
  const list = Array.isArray(items) ? [...items] : [];
  return list.sort((a, b) => {
    const pa = Number(a?.position ?? 0);
    const pb = Number(b?.position ?? 0);
    if (pa !== pb) return pa - pb;
    return Number(a?.created_at ?? 0) - Number(b?.created_at ?? 0);
  });
}

export function formatCollectionStepTitle(item) {
  if (!item) return "";
  const title = String(item.title || "Untitled");
  return item.year ? `${title} (${item.year})` : title;
}

export function isPublished(list) {
  return Boolean(list && list.visibility === "published");
}

/**
 * Compute the two position updates needed to move an item up or down by one.
 * Returns `[]` when the move is a no-op (edge of list). Positions are
 * renormalized to their index so swaps stay stable across repeated moves.
 *
 * @returns {Array<{id:string, position:number}>}
 */
export function computeReorder(items, itemId, direction) {
  const ordered = orderCollectionSteps(items).map((item, index) => ({
    ...item,
    position: index,
  }));
  const idx = ordered.findIndex((item) => String(item.id) === String(itemId));
  if (idx === -1) return [];
  const swapWith = direction === "up" ? idx - 1 : idx + 1;
  if (swapWith < 0 || swapWith >= ordered.length) return [];
  const a = ordered[idx];
  const b = ordered[swapWith];
  return [
    { id: a.id, position: b.position },
    { id: b.id, position: a.position },
  ];
}

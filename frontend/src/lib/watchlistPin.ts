import type { LibraryItem } from "../api/types";
/** Whether a title card should show Pin-to-watchlist affordances. */
export function allowWatchlistPin(item: LibraryItem | null | undefined) {
  if (!item) return false;
  if (item.card_kind === "purge" || item.purge_candidate === true) return false;
  return true;
}

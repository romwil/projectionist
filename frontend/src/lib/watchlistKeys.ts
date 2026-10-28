import type {LibraryItem, JsParam} from "../api/types";
export function watchlistItemKey(item: LibraryItem | null | undefined) {
  const mediaType = item?.media_type || "movie";
  const tmdb = item?.tmdb_id ?? "";
  const tvdb = item?.tvdb_id ?? "";
  return `${mediaType}:${tmdb}:${tvdb}`;
}

export function buildWatchlistLookup(pins: JsParam[] = []) {
  const byItemKey = new Map();
  const byId = new Map();
  for (const pin of pins) {
    byItemKey.set(watchlistItemKey(pin as JsParam), pin);
    byId.set((pin as JsParam).id, pin);
  }
  return { byItemKey, byId };
}

import type {JsonObject, JsParam} from "../api/types";
/** Filter chat threads for sidebar search. */

export function filterThreads(threads: JsParam, query: string) {
  const list = Array.isArray(threads) ? threads : [];
  const q = String(query || "").trim().toLowerCase();
  if (!q) return list;
  return list.filter((thread) => {
    const title = String(thread?.thread_title || "").toLowerCase();
    const preview = String(thread?.preview || "").toLowerCase();
    return title.includes(q) || preview.includes(q);
  });
}

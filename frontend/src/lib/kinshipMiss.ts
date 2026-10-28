import type {JsonObject, JsParam} from "../api/types";
/** Owner-facing kinship_miss demand list helpers. */

export const KINSHIP_MISS_WHY_LABELS: Record<string, any> = {
  more_like_this_empty: "Empty More Like This",
  related_empty: "Empty Related titles",
  relations_empty: "Empty Related titles",
  bridge_zero_peers: "Bridge with zero peers",
};

export function kinshipMissWhyLabel(why: JsParam) {
  const key = String(why || "").trim();
  if (!key) return "Empty shelf";
  return KINSHIP_MISS_WHY_LABELS[key] || key.replaceAll("_", " ");
}

export function formatKinshipMissHit(count: unknown) {
  const n = Number(count) || 0;
  return n === 1 ? "1 miss" : `${n.toLocaleString()} misses`;
}

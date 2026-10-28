import type {JsonObject, JsParam} from "../api/types";
export function shouldShowBulkActionProgress({ total, asynchronous = false }: JsParam = {}) {
  return Number(total) > 1 || Boolean(asynchronous);
}

export function bulkActionProgressView({ label = "Working", current = 0, total = 0 }: JsParam = {}) {
  const safeTotal = Math.max(0, Number(total) || 0);
  const safeCurrent = Math.min(Math.max(0, Number(current) || 0), safeTotal);
  const percent = safeTotal ? Math.round((safeCurrent / safeTotal) * 100) : 0;
  const suffix = String(label).endsWith("…") ? "" : "…";

  return {
    label: `${label}${suffix}`,
    count: safeTotal ? `${safeCurrent} / ${safeTotal}` : "",
    percent,
  };
}

/** Household pulse (Admin Overview): copy and shapes for on-box weekly totals. */

export type PulseGuardrail = {
  id: string;
  label: string;
  value: number | null;
  limit: number | null;
  status: "ok" | "watch" | "info" | "no_data";
};

export type HouseholdPulse = {
  telemetry_enabled?: boolean;
  north_star: { label: string; this_week: number; last_week: number; weekly: number[] };
  guardrails: PulseGuardrail[];
  box?: { write_queue_depth?: number | null; api_p95_ms?: number | null };
};

export function weekOverWeek(thisWeek: number, lastWeek: number): { direction: "up" | "down" | "flat"; text: string } {
  const now = Number(thisWeek) || 0;
  const prev = Number(lastWeek) || 0;
  const diff = now - prev;
  if (diff > 0) return { direction: "up", text: `Up ${diff} from last week` };
  if (diff < 0) return { direction: "down", text: `Down ${-diff} from last week` };
  return { direction: "flat", text: "Same as last week" };
}

/** SVG polyline points for a small sparkline; oldest week first. */
export function sparklinePoints(values: number[], width = 96, height = 24): string {
  const nums = (values || []).map((v) => Number(v) || 0);
  if (!nums.length) return "";
  const max = Math.max(1, ...nums);
  const step = nums.length > 1 ? width / (nums.length - 1) : 0;
  return nums
    .map((v, i) => `${Math.round(i * step * 10) / 10},${Math.round((height - (v / max) * height) * 10) / 10}`)
    .join(" ");
}

export function sparklineLabel(values: number[]): string {
  const nums = (values || []).map((v) => Number(v) || 0);
  return `Last ${nums.length} weeks, oldest first: ${nums.join(", ")}`;
}

export function guardrailValueText(guard: PulseGuardrail): string {
  if (guard.value === null || guard.value === undefined) return "No data yet";
  const v = Number(guard.value);
  switch (guard.id) {
    case "chat_failure_rate":
      return `${Math.round(v * 1000) / 10}% (limit ${Math.round((guard.limit ?? 0) * 100)}%)`;
    case "chat_p95_ms":
      return `${Math.round(v / 100) / 10} s (limit ${Math.round((guard.limit ?? 0) / 1000)} s)`;
    case "llm_spend":
      return `$${v.toFixed(2)}`;
    default:
      return String(v);
  }
}

const STATUS_COPY: Record<PulseGuardrail["status"], string> = {
  ok: "OK",
  watch: "Watch",
  info: "Info",
  no_data: "No data",
};

export function guardrailStatusCopy(status: PulseGuardrail["status"]): string {
  return STATUS_COPY[status] || "Info";
}

import type {JsonObject, LibraryItem, JsParam} from "../api/types";
/** Helpers for the seasonal-shelf editor on the Live setup (same store as Holidays). */

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

const MOVABLE_LABELS: Record<string, any> = {
  arbor_day: "Last Friday of April",
  labor_day: "First Monday of September",
  thanksgiving: "Fourth Thursday of November",
};

export function termsToInput(terms: JsParam) {
  return Array.isArray(terms) ? terms.join(", ") : String(terms || "");
}

export function inputToTerms(value: unknown) {
  return String(value || "")
    .split(/[\n,]+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

/** "Oct 31" for fixed days, the rule for movable ones. */
export function shelfDateLabel(item: LibraryItem | null | undefined) {
  if (!item) return "";
  if (item.kind === "movable") {
    return MOVABLE_LABELS[item.movable_rule] || "Moves each year";
  }
  const month = Number(item.month);
  const day = Number(item.day);
  if (!month || !day || month < 1 || month > 12) return "";
  return `${MONTHS[month - 1]} ${day}`;
}

/** New id order after moving the row at `index` by `delta` (−1 up, +1 down). */
export function moveShelfId(ids: JsParam, index: unknown, delta: unknown) {
  const list = Array.isArray(ids) ? [...ids] : [];
  const target = (index as JsParam) + (delta as JsParam);
  if ((index as JsParam) < 0 || (index as JsParam) >= list.length || target < 0 || target >= list.length) return list;
  const [moved] = list.splice(Number(index), 1);
  list.splice(target, 0, moved);
  return list;
}

/** Ids to save when adding a title at the front of the shelf (no duplicates). */
export function addShelfIdFirst(ids: JsParam, id: string | number) {
  const next = (Array.isArray(ids) ? ids : []).filter((value) => Number(value) !== Number(id));
  return [Number(id), ...next.map(Number)];
}

/** Why a title sits where it does, in plain words. */
export function shelfRoleLabel(role?: string | number | null, { hasNote = false }: JsParam = {}) {
  if (hasNote) return "Staff pick";
  if (role === "pin") return "Picked by you";
  if (role === "include") return "Added by you";
  return "Matches the season";
}

/** Staff-pick line under a seasonal Explore poster. */
export function seasonalCardMeta(item: LibraryItem | null | undefined) {
  const note = String(item?.curator_note || item?.why || "").trim();
  if (note) return note;
  return item?.anniversary_text || item?.anniversary_context || null;
}

/**
 * Opening user message when chatting about one seasonal pick (Explore members
 * and Admin Live owner tools share the same seed shape).
 */
export function seasonalPickChatSeed(
  {
  seasonLabel,
  shelfName,
  scopeId,
  title,
  year,
  curatorNote,
  railRole,
}: JsParam = {},
) {
  const label = String(seasonLabel || shelfName || "this season").trim() || "this season";
  const name = String(title || "this title").trim() || "this title";
  const yearBit = year ? ` (${year})` : "";
  const note = String(curatorNote || "").trim();
  const role = String(railRole || "").trim();
  const scope = String(scopeId || "").trim();
  const parts = [
    `We're looking at the ${label} seasonal picks on Explore.`,
    `Focus title: "${name}"${yearBit}.`,
  ];
  if (scope) parts.push(`Season scope: ${scope}.`);
  if (note) parts.push(`Curator note: ${note}`);
  if (role) parts.push(`Shelf role: ${role}.`);
  parts.push(
    "Talk through why this belongs on the shelf this year, suggest library alternatives, or deepen the staff-pick note — keep the professor voice.",
  );
  return parts.join(" ");
}

/** @deprecated Prefer seasonalPickChatSeed — kept for older Admin call sites. */
export function shelfChatSeedMessage(args: JsParam = {}) {
  return seasonalPickChatSeed(args);
}

export const SHELF_PICK_ROLES = [
  "Classic",
  "Family",
  "New this year",
  "Deep cut",
  "After bedtime",
] as const;

export const DEFAULT_ROLE_MIX: Record<string, number> = {
  Classic: 3,
  Family: 3,
  "New this year": 1,
  "Deep cut": 2,
  "After bedtime": 1,
};

/** Explore rail header: "Christmas — [theme]" when the shelf has a theme. */
export function seasonalRailTitle(meta: { label?: string; theme?: string } | null | undefined) {
  const label = String(meta?.label || "Seasonal picks").trim() || "Seasonal picks";
  const theme = String(meta?.theme || "").trim();
  if (!theme) return label;
  return `${label} — ${theme}`;
}

/** Left-rail state for one observance. */
export function observanceListState(
  item: { enabled?: boolean; id?: string } | null | undefined,
  schedule: Array<{ id?: string; active_now?: boolean }> | null | undefined,
) {
  if (!item || item.enabled === false) return "Off";
  const row = (schedule || []).find((entry) => entry?.id === item.id);
  if (row?.active_now) return "On Explore now";
  return "Coming up";
}

/** Summary under the holiday name: dates, shelf size, Live block. */
export function holidaySummary({
  item,
  schedule,
  shelfCount = 0,
}: {
  item?: { id?: string; schedule_publish?: boolean; grounding_date_label?: string } | null;
  schedule?: Array<{ id?: string; window_start?: string; window_end?: string }> | null;
  shelfCount?: number;
} = {}) {
  const row = (schedule || []).find((entry) => entry?.id === item?.id);
  const dates = row?.window_start
    ? `${row.window_start} – ${row.window_end || row.window_start}`
    : String(item?.grounding_date_label || "Dates follow the calendar");
  const size = shelfCount === 1 ? "1 on the shelf" : `${shelfCount} on the shelf`;
  const live = item?.schedule_publish === false ? "Live block off" : "Live block on";
  return `${dates} · ${size} · ${live}`;
}

export function shelfPickRole(role?: string | null) {
  const text = String(role || "").trim();
  return (SHELF_PICK_ROLES as readonly string[]).includes(text) ? text : "";
}

/**
 * What one click on "Ask the professor to curate" should do.
 * A failed or empty professor reply is an error the shelf must show.
 * A real proposal stays a preview until the owner applies it.
 * A pick with an empty note never ships.
 */
export function curateClickPlan({ error = null, proposal = null }: JsParam = {}) {
  if (error) {
    const message = String(error).trim() || "The professor couldn't curate this shelf.";
    return { ok: false, stage: "preview", theme: "", message, applyPicks: [] };
  }
  const picks = Array.isArray(proposal?.picks) ? proposal.picks : [];
  const theme = String(proposal?.theme || "").trim();
  const applyPicks: JsParam[] = [];
  for (const pick of picks) {
    const libraryItemId = Number(pick?.library_item_id || pick?.id);
    if (!Number.isFinite(libraryItemId) || libraryItemId < 1) continue;
    const note = String(pick?.curator_note || pick?.note || "").trim();
    if (!note) continue;
    const next: JsParam = {
      library_item_id: libraryItemId,
      curator_note: note,
    };
    const role = shelfPickRole(pick?.role || pick?.shelf_role);
    if (role) next.role = role;
    const because = String(pick?.matched_because || "").trim();
    if (because) next.matched_because = because;
    applyPicks.push(next);
  }
  if (!applyPicks.length) {
    return {
      ok: false,
      stage: "preview",
      theme,
      message: "The professor didn't return any picks for this shelf.",
      applyPicks: [],
    };
  }
  return { ok: true, stage: "preview", theme, message: "", applyPicks };
}

/**
 * Cards to show after a professor curate. Keyword/anniversary dump rows drop.
 * A hand pin (replacesMatches false) still keeps the rest of the shelf.
 */
export function visibleCuratedShelf(items: LibraryItem[] | null | undefined, { replacesMatches = false }: JsParam = {}) {
  const rows = Array.isArray(items) ? items : [];
  if (!replacesMatches) return rows;
  const kept = rows.filter((row) => row?.rail_role === "pin" || row?.rail_role === "include");
  return kept.length ? kept : rows;
}

/** Fields the owner edits per shelf (PATCH body for the existing holidays API). */
export function shelfPatchFromForm(form: JsParam, item: LibraryItem | null | undefined) {
  const patch: JsParam = {
    name: String(form.name || "").trim(),
    pre_shoulder_days: Math.max(0, Number(form.pre_shoulder_days) || 0),
    post_shoulder_days: Math.max(0, Number(form.post_shoulder_days) || 0),
    search_terms: inputToTerms(form.search_terms),
    enabled: Boolean(form.enabled),
  };
  if (item?.kind !== "movable") {
    patch.month = Number(form.month) || item?.month || 1;
    patch.day = Number(form.day) || item?.day || 1;
  }
  return patch;
}

export function shelfFormFromItem(item: LibraryItem | null | undefined) {
  return {
    name: item?.name || "",
    month: item?.month ?? 1,
    day: item?.day ?? 1,
    pre_shoulder_days: item?.pre_shoulder_days ?? 7,
    post_shoulder_days: item?.post_shoulder_days ?? 2,
    search_terms: termsToInput(item?.search_terms),
    enabled: item?.enabled !== false,
  };
}

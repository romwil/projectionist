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

const MOVABLE_LABELS = {
  arbor_day: "Last Friday of April",
  labor_day: "First Monday of September",
  thanksgiving: "Fourth Thursday of November",
};

export function termsToInput(terms) {
  return Array.isArray(terms) ? terms.join(", ") : String(terms || "");
}

export function inputToTerms(value) {
  return String(value || "")
    .split(/[\n,]+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

/** "Oct 31" for fixed days, the rule for movable ones. */
export function shelfDateLabel(item) {
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
export function moveShelfId(ids, index, delta) {
  const list = Array.isArray(ids) ? [...ids] : [];
  const target = index + delta;
  if (index < 0 || index >= list.length || target < 0 || target >= list.length) return list;
  const [moved] = list.splice(index, 1);
  list.splice(target, 0, moved);
  return list;
}

/** Ids to save when adding a title at the front of the shelf (no duplicates). */
export function addShelfIdFirst(ids, id) {
  const next = (Array.isArray(ids) ? ids : []).filter((value) => Number(value) !== Number(id));
  return [Number(id), ...next.map(Number)];
}

/** Why a title sits where it does, in plain words. */
export function shelfRoleLabel(role, { hasNote = false } = {}) {
  if (hasNote) return "Staff pick";
  if (role === "pin") return "Picked by you";
  if (role === "include") return "Added by you";
  return "Matches the season";
}

/** Staff-pick line under a seasonal Explore poster. */
export function seasonalCardMeta(item) {
  const note = String(item?.curator_note || item?.why || "").trim();
  if (note) return note;
  return item?.anniversary_text || item?.anniversary_context || null;
}

/**
 * Opening user message when chatting about one seasonal pick (Explore members
 * and Admin Live owner tools share the same seed shape).
 */
export function seasonalPickChatSeed({
  seasonLabel,
  shelfName,
  scopeId,
  title,
  year,
  curatorNote,
  railRole,
} = {}) {
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
export function shelfChatSeedMessage(args = {}) {
  return seasonalPickChatSeed(args);
}

/** Fields the owner edits per shelf (PATCH body for the existing holidays API). */
export function shelfPatchFromForm(form, item) {
  const patch = {
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

export function shelfFormFromItem(item) {
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

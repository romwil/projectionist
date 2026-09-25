/** Selection defaults and copy for Admin → Libraries Investigate (v1.36.0). */

export const STILLS_LEAVE_LAN =
  "When vision is on, three stills leave the LAN so the chat LLM can look at them.";

export const SCENE_NAMES_NOT_EVIDENCE =
  "Scene names and SxxEyy in the filename are a claim, not evidence.";

export function defaultRowSelected(row) {
  if (!row) return false;
  if (row.same_show === false) return false;
  if (typeof row.selected_default === "boolean") return row.selected_default;
  const confidence = String(row.confidence || "").toLowerCase();
  return confidence === "certain" || confidence === "likely";
}

export function selectedFileIds(rows, selected) {
  return (rows || [])
    .filter((row) => selected[row.id] && row.same_show !== false)
    .map((row) => String(row.id));
}

export function selectionMap(rows) {
  const next = {};
  for (const row of rows || []) {
    next[row.id] = defaultRowSelected(row);
  }
  return next;
}

export function confidenceLabel(confidence) {
  const key = String(confidence || "").toLowerCase();
  if (key === "certain") return "Certain";
  if (key === "likely") return "Likely";
  return "Uncertain";
}

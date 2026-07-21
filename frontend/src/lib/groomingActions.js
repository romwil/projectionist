/** Helpers for the reversible grooming-action (safe undo) UI. Pure logic. */

export function canUndoGroomingAction(action) {
  if (!action || typeof action !== "object") return false;
  if (action.undone_at != null) return false;
  return Number(action.item_count) > 0;
}

export function groomingActionStatusLabel(action) {
  if (!action || typeof action !== "object") return "";
  if (action.undone_at != null) return "Undone";
  return canUndoGroomingAction(action) ? "Undoable" : "Not reversible";
}

/** Human line describing one grooming action for the list. */
export function formatGroomingActionLine(action) {
  if (!action || typeof action !== "object") return "";
  const summary = String(action.summary || "Grooming action").trim();
  const when = action.created_at ? formatWhen(action.created_at) : "";
  return when ? `${summary} · ${when}` : summary;
}

function formatWhen(epochSeconds) {
  const ms = Number(epochSeconds) * 1000;
  if (!Number.isFinite(ms)) return "";
  try {
    return new Date(ms).toLocaleString();
  } catch {
    return "";
  }
}

/** Message after a successful undo. */
export function formatUndoSuccess(result) {
  const restored = Number(result?.restored) || 0;
  return `Restored ${restored} title${restored === 1 ? "" : "s"} to the library index.`;
}

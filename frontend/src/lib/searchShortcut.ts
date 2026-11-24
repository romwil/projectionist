/** Ctrl+K or Command+K opens Search from anywhere, including a text field. */
export function isSearchShortcut(
  event: {
    key?: string;
    metaKey?: boolean;
    ctrlKey?: boolean;
    altKey?: boolean;
  } | null,
) {
  if (!event || event.altKey) return false;
  if (!event.metaKey && !event.ctrlKey) return false;
  return String(event.key || "").toLowerCase() === "k";
}

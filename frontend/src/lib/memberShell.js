/**
 * Resolve which member shell to render (distinct youth / guest layouts).
 * @param {{ role?: string, isYouth?: boolean, multiUserEnabled?: boolean }} opts
 * @returns {'youth' | 'guest' | 'default'}
 */
export function resolveMemberShell({ role = "owner", isYouth = false, multiUserEnabled = false } = {}) {
  if (!multiUserEnabled) return "default";
  const normalized = String(role || "owner").toLowerCase();
  if (normalized === "guest") return "guest";
  if (isYouth) return "youth";
  return "default";
}

/**
 * Root class names for the active shell.
 * @param {string} shell
 * @param {string} [base]
 */
export function shellRootClass(shell, base = "app-root") {
  if (shell === "youth") return `${base} app-root--youth youth-shell`;
  if (shell === "guest") return `${base} app-root--guest guest-shell`;
  return base;
}

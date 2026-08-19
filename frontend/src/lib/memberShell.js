/**
 * Resolve which member shell to render (distinct youth / guest layouts).
 * @param {{ role?: string, isYouth?: boolean, multiUserEnabled?: boolean }} opts
 * @returns {'youth' | 'guest' | 'default'}
 */
export function resolveMemberShell({ role = "owner", isYouth = false, multiUserEnabled = false } = {}) {
  void role;
  if (!multiUserEnabled) return "default";
  if (isYouth) return "youth";
  return "default";
}

/**
 * Legacy guests are members. Deep-link blocking for a third role is gone.
 *
 * @param {{ role?: string, multiUserEnabled?: boolean, authReady?: boolean }} opts
 */
export function guestDeepLinkBlocked({
  role = "owner",
  multiUserEnabled = false,
  authReady = true,
} = {}) {
  void role;
  void multiUserEnabled;
  void authReady;
  return false;
}

/**
 * Root class names for the active shell.
 * @param {string} shell
 * @param {string} [base]
 */
export function shellRootClass(shell, base = "app-root") {
  if (shell === "youth") return `${base} app-root--youth youth-shell`;
  return base;
}

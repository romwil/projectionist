/**
 * The one sign-out path. Every "Sign out" control calls ``signOut``.
 *
 * Shared household tablets are normal, so the next person must not inherit the
 * previous account's role snapshot, chat thread pointer, or cached rails.
 */

import { logout } from "../api/client.js";
import { clearAuthSnapshot } from "./authGate.js";
import { clearExploreHubCache } from "./exploreHubCache.js";
import { RAIL_SEED_STORAGE_KEY } from "./railChatSeed.js";
import { TONIGHT_QUEUE_KEY } from "./tonightQueue.js";

type KeyStore = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export const PER_USER_LOCAL_KEYS = ["curatorx_session", "curatorx_active_lens"];
export const PER_USER_SESSION_KEYS = [RAIL_SEED_STORAGE_KEY, TONIGHT_QUEUE_KEY];

function safeStorage(kind: "localStorage" | "sessionStorage"): KeyStore | null {
  try {
    return (globalThis as Record<string, unknown>)[kind] as KeyStore | null;
  } catch {
    return null;
  }
}

export function clearPerUserClientState({
  local = safeStorage("localStorage"),
  session = safeStorage("sessionStorage"),
}: { local?: KeyStore | null; session?: KeyStore | null } = {}) {
  for (const key of PER_USER_LOCAL_KEYS) {
    try {
      local?.removeItem(key);
    } catch {
      // storage unavailable
    }
  }
  for (const key of PER_USER_SESSION_KEYS) {
    try {
      session?.removeItem(key);
    } catch {
      // storage unavailable
    }
  }
  clearExploreHubCache(session);
}

export async function signOut({
  logoutFn = logout,
  clearSnapshot = clearAuthSnapshot,
  clearClientState = clearPerUserClientState,
  navigateTo = (path: string) => globalThis.location.replace(path),
}: {
  logoutFn?: () => Promise<unknown>;
  clearSnapshot?: () => void;
  clearClientState?: () => void;
  navigateTo?: (path: string) => void;
} = {}) {
  try {
    await logoutFn();
  } catch {
    // Still clear local state and leave: the cookie may already be gone.
  }
  clearSnapshot();
  clearClientState();
  // Full load, not SPA navigation, so in-memory caches from the last account go too.
  navigateTo("/login");
}

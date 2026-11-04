/**
 * One in-flight auth read for the whole page.
 *
 * Browse shells, the inbox, and every poster menu each called useAuthGate.
 * That fanned out into a getFeatures + getAuthMe pair per card. Each of those
 * opens SQLite, and a contended file can sit on the 30s busy timeout — so an
 * inbox of unread cards looked hung. Concurrent callers share one promise.
 * A signed-in (or single-user) result is reused; a logged-out result is not,
 * so a later login still refetches.
 */

import { getAuthMe, getFeatures } from "../api/client.js";
import type {AuthMe, Features, JsonObject, JsParam} from "../api/types";

export async function fetchAuthSnapshot(getFeaturesFn: () => Promise<Features | null | undefined>, getAuthMeFn: () => Promise<AuthMe | null | undefined>) {
  let enabled = false;
  try {
    const features = await getFeaturesFn();
    enabled = Boolean(features?.features?.multi_user_enabled);
    const seerrEnabled = Boolean(features?.features?.seerr_enabled);
    const llmConfigured = Boolean(features?.features?.llm_configured);
    if (features?.setup_state === "setup") {
      return {
        ok: true,
        cacheable: false,
        setup: true,
        needsLogin: false,
        features,
        multiUserEnabled: enabled,
        seerrEnabled,
        llmConfigured,
        authenticated: false,
        role: "",
        isOwner: false,
        isYouth: false,
        user: null,
      };
    }
    if (!enabled) {
      return {
        ok: true,
        cacheable: true,
        setup: false,
        needsLogin: false,
        features,
        multiUserEnabled: false,
        seerrEnabled,
        llmConfigured,
        authenticated: true,
        role: "owner",
        isOwner: true,
        isYouth: false,
        user: features?.user || null,
      };
    }
    const me = await getAuthMeFn();
    if (!me?.user) {
      return {
        ok: true,
        cacheable: false,
        setup: false,
        needsLogin: true,
        features,
        multiUserEnabled: true,
        seerrEnabled,
        llmConfigured,
        authenticated: false,
        role: "",
        isOwner: false,
        isYouth: false,
        user: null,
      };
    }
    const rawRole = String(me.user?.role || "member").toLowerCase();
    const role = rawRole === "owner" ? "owner" : "member";
    return {
      ok: true,
      cacheable: true,
      setup: false,
      needsLogin: false,
      features,
      multiUserEnabled: true,
      seerrEnabled,
      llmConfigured,
      authenticated: true,
      role,
      isOwner: role === "owner",
      isYouth: Boolean(me.user?.is_youth),
      autoconfirmAdds: role === "member" && !me.user?.is_youth && Boolean(me.user?.autoconfirm_adds),
      user: me.user,
    };
  } catch {
    if (enabled) {
      return {
        ok: false,
        cacheable: false,
        setup: false,
        needsLogin: true,
        features: null,
        multiUserEnabled: true,
        seerrEnabled: false,
        llmConfigured: false,
        authenticated: false,
        role: "",
        isOwner: false,
        isYouth: false,
        user: null,
      };
    }
    return {
      ok: false,
      cacheable: false,
      setup: false,
      needsLogin: false,
      features: null,
      multiUserEnabled: false,
      seerrEnabled: false,
      llmConfigured: false,
      authenticated: true,
      role: "owner",
      isOwner: true,
      isYouth: false,
      user: null,
    };
  }
}

/**
 * @param {{ redirect?: boolean }} [options]
 */
export function applyAuthSnapshot(snap: JsParam, { redirect = true }: JsParam = {}) {
  if (snap?.setup) {
    return {
      navigateTo: "/setup",
      authReady: false,
      multiUserEnabled: Boolean(snap.multiUserEnabled),
      seerrEnabled: Boolean(snap.seerrEnabled),
      llmConfigured: Boolean(snap.llmConfigured),
      defaultPage: "auto",
      isOwner: false,
      role: "",
      isYouth: false,
      authenticated: false,
    };
  }
  if (snap?.needsLogin) {
    if (redirect) {
      return {
        navigateTo: "/login",
        authReady: false,
        multiUserEnabled: true,
        seerrEnabled: Boolean(snap.seerrEnabled),
        llmConfigured: Boolean(snap.llmConfigured),
        defaultPage: "auto",
        isOwner: false,
        role: "",
        isYouth: false,
        authenticated: false,
      };
    }
    return {
      navigateTo: null,
      authReady: true,
      multiUserEnabled: true,
      seerrEnabled: Boolean(snap.seerrEnabled),
      llmConfigured: Boolean(snap.llmConfigured),
      defaultPage: "auto",
      isOwner: false,
      role: "",
      isYouth: false,
      authenticated: false,
    };
  }
  return {
    navigateTo: null,
    authReady: Boolean(snap),
    multiUserEnabled: Boolean(snap?.multiUserEnabled),
    seerrEnabled: Boolean(snap?.seerrEnabled),
    llmConfigured: Boolean(snap?.llmConfigured),
    defaultPage: String(snap?.user?.default_page || "auto"),
    isOwner: snap?.isOwner !== false,
    role: snap?.role || "owner",
    isYouth: Boolean(snap?.isYouth),
    authenticated: snap?.authenticated !== false,
  };
}

export function createAuthSnapshotStore({
  getFeatures: getFeaturesFn = getFeatures,
  getAuthMe: getAuthMeFn = getAuthMe,
}: {
  getFeatures?: () => Promise<JsParam>;
  getAuthMe?: () => Promise<JsParam>;
} = {}) {
  let snapshot: JsParam = null;
  let inflight: Promise<JsParam> | null = null;
  let generation = 0;
  let sessionUser: JsParam;
  let sessionInflight: Promise<JsParam> | null = null;

  return {
    peek() {
      return snapshot;
    },
    clear() {
      generation += 1;
      snapshot = null;
      inflight = null;
      sessionUser = undefined;
      sessionInflight = null;
    },
    load() {
      if (snapshot) return Promise.resolve(snapshot);
      if (inflight) return inflight;
      const gen = generation;
      inflight = fetchAuthSnapshot(getFeaturesFn, getAuthMeFn)
        .then((next) => {
          if (gen === generation && next.cacheable) snapshot = next;
          return next;
        })
        .finally(() => {
          if (gen === generation) inflight = null;
        });
      return inflight;
    },
    loadSessionUser() {
      if (sessionUser !== undefined) return Promise.resolve(sessionUser);
      if (sessionInflight) return sessionInflight;
      const gen = generation;
      sessionInflight = Promise.resolve()
        .then(() => getAuthMeFn())
        .then((me) => {
          const user = me?.user || null;
          if (gen === generation) sessionUser = user;
          return user;
        })
        .catch(() => null)
        .finally(() => {
          if (gen === generation) sessionInflight = null;
        });
      return sessionInflight;
    },
  };
}

const sharedAuth = createAuthSnapshotStore({ getFeatures, getAuthMe });

export function peekAuthSnapshot() {
  return sharedAuth.peek();
}

/** True when the cached signed-in viewer is a Youth account (false before auth loads). */
export function peekViewerIsYouth(): boolean {
  return Boolean((sharedAuth.peek() as JsParam)?.isYouth);
}

/** True when the owner lets this adult member add to Radarr/Sonarr without their confirm. */
export function peekViewerAutoconfirmsAdds(): boolean {
  return Boolean((sharedAuth.peek() as JsParam)?.autoconfirmAdds);
}

export function clearAuthSnapshot() {
  sharedAuth.clear();
}

export function loadAuthSnapshot() {
  return sharedAuth.load();
}

export function loadAuthSessionUser() {
  return sharedAuth.loadSessionUser();
}

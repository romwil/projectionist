import type {Features, JsonObject, JsParam} from "../api/types";
/**
 * Whether this install's icon bar includes Live before /api/features returns.
 *
 * The HTML shell can stamp the flag from settings (no session, no SQLite).
 * A later features response updates the same localStorage key so client-side
 * route changes keep the same peers while auth is still in flight.
 */

export const LIVE_NAV_READY_KEY = "projectionist.liveChannelsReady.v1";

export function readCachedLiveChannelsReady(storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null | undefined = globalThis.localStorage) {
  try {
    return storage?.getItem(LIVE_NAV_READY_KEY) === "1";
  } catch {
    return false;
  }
}

export function writeCachedLiveChannelsReady(ready: JsParam, storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null | undefined = globalThis.localStorage) {
  try {
    if (!storage) return;
    if (ready) storage.setItem(LIVE_NAV_READY_KEY, "1");
    else storage.removeItem(LIVE_NAV_READY_KEY);
  } catch {
    // storage unavailable / quota
  }
}

/** @returns {boolean|null} null when this document was not stamped */
export function readBootLiveChannelsReady() {
  if (typeof globalThis.window === "undefined") return null;
  const boot = globalThis.window.__PROJECTIONIST_NAV__;
  if (!boot || typeof boot.liveChannelsReady !== "boolean") return null;
  return boot.liveChannelsReady;
}

export function initialLiveChannelsReady(storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null | undefined = globalThis.localStorage) {
  const boot = readBootLiveChannelsReady();
  if (boot !== null) {
    writeCachedLiveChannelsReady(boot, storage);
    return boot;
  }
  return readCachedLiveChannelsReady(storage);
}

/**
 * Authenticated /api/features includes the flag. The public payload omits it
 * and must not clear a known Live install.
 * @returns {boolean|null}
 */
export function liveChannelsReadyFromFeatures(features: Features | null | undefined) {
  const flags = features?.features;
  if (!flags || !Object.prototype.hasOwnProperty.call(flags, "live_channels_ready")) {
    return null;
  }
  return Boolean(flags.live_channels_ready);
}

export function applyLiveChannelsFeature(features: Features | null | undefined, setReady: (ready: boolean) => void, storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null | undefined = globalThis.localStorage) {
  const ready = liveChannelsReadyFromFeatures(features);
  if (ready === null) return null;
  writeCachedLiveChannelsReady(ready, storage);
  if (typeof setReady === "function") setReady(ready);
  return ready;
}

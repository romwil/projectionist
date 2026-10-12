/**
 * `/live` first paint. A cached guide shows immediately. A hung guide request
 * becomes an error instead of leaving "Filling in the guide…" up.
 */

export const LIVE_GUIDE_CACHE_KEY = "projectionist.liveGuide.v1";
export const LIVE_GUIDE_WAIT_MS = 8000;
export const LIVE_GUIDE_STALL_MESSAGE = "The guide did not finish loading.";

export function readLiveGuideCache(storage = globalThis.sessionStorage) {
  if (!storage) return null;
  try {
    const parsed = JSON.parse(storage.getItem(LIVE_GUIDE_CACHE_KEY) || "null");
    const guide = parsed?.guide;
    if (!guide?.ready || !Array.isArray(guide.channels) || guide.channels.length === 0) {
      return null;
    }
    return { ...guide, warming: false, stale: true };
  } catch {
    return null;
  }
}

export function writeLiveGuideCache(guide, storage = globalThis.sessionStorage) {
  if (!storage || !guide?.ready || !guide.channels?.length) return;
  try {
    storage.setItem(
      LIVE_GUIDE_CACHE_KEY,
      JSON.stringify({
        savedAt: Date.now(),
        guide: { ...guide, warming: false, stale: false },
      }),
    );
  } catch {
    // sessionStorage unavailable / quota
  }
}

export function shouldShowGuideSkeleton({ guide, error, loading, gaveUp } = {}) {
  if (gaveUp || error) return false;
  if (guide?.ready && guide.channels?.length) return false;
  return Boolean(loading || guide?.warming);
}

export function guideStallError({ guide, gaveUp, error } = {}) {
  if (guide?.ready && guide.channels?.length) return "";
  if (error) return error;
  if (gaveUp) return LIVE_GUIDE_STALL_MESSAGE;
  return "";
}

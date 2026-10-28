import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  LIVE_GUIDE_STALL_MESSAGE,
  guideStallError,
  readLiveGuideCache,
  shouldShowGuideSkeleton,
  writeLiveGuideCache,
} from "./liveGuidePaint.ts";

function memoryStorage() {
  const storage = new Map();
  return {
    getItem: (key) => (storage.has(key) ? storage.get(key) : null),
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: (key) => storage.delete(key),
  };
}

const readyGuide = {
  ready: true,
  warming: false,
  channels: [{ id: "ch-1", name: "Kung Fu Theater" }],
};

describe("live guide paint", () => {
  it("shows a cached guide immediately and does not keep the skeleton", () => {
    const storage = memoryStorage();
    writeLiveGuideCache(readyGuide, storage);
    const cached = readLiveGuideCache(storage);
    assert.equal(cached.ready, true);
    assert.equal(cached.channels[0].name, "Kung Fu Theater");
    assert.equal(
      shouldShowGuideSkeleton({ guide: cached, error: "", loading: true, gaveUp: false }),
      false,
    );
  });

  it("does not cache a warming skeleton", () => {
    const storage = memoryStorage();
    writeLiveGuideCache({ ready: false, warming: true, channels: [] }, storage);
    assert.equal(readLiveGuideCache(storage), null);
  });

  it("replaces a hung warming poll with an error instead of a permanent skeleton", () => {
    const warming = { ready: false, warming: true, channels: [] };
    assert.equal(
      shouldShowGuideSkeleton({ guide: warming, error: "", loading: false, gaveUp: false }),
      true,
    );
    assert.equal(
      shouldShowGuideSkeleton({ guide: warming, error: "", loading: true, gaveUp: true }),
      false,
    );
    assert.equal(guideStallError({ guide: warming, gaveUp: true, error: "" }), LIVE_GUIDE_STALL_MESSAGE);
    assert.equal(guideStallError({ guide: readyGuide, gaveUp: true, error: "nope" }), "");
  });
});

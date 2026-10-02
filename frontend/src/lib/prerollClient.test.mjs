import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { normalizePrerollPayload, shouldPlayMoviePreroll } from "./prerollClient.js";

describe("prerollClient", () => {
  it("normalizes next-preroll payloads and rejects empties", () => {
    assert.equal(normalizePrerollPayload(null), null);
    assert.equal(normalizePrerollPayload({ id: "a" }), null);
    const ok = normalizePrerollPayload({
      id: "clip-1",
      url: "/api/preroll/asset/clip-1",
      title: "Bumper",
    });
    assert.equal(ok.id, "clip-1");
    assert.equal(ok.url, "/api/preroll/asset/clip-1");
    assert.equal(ok.title, "Bumper");
  });

  it("gates movie preroll vs episode", () => {
    assert.equal(shouldPlayMoviePreroll({ media_type: "movie" }), true);
    assert.equal(shouldPlayMoviePreroll({ media_type: "episode" }), false);
    assert.equal(shouldPlayMoviePreroll({ media_type: "episode" }, { force: true }), true);
  });
});

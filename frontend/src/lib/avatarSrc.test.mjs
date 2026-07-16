import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { resolveAvatarSrc } from "./avatarSrc.js";

describe("resolveAvatarSrc", () => {
  it("passes through absolute URLs", () => {
    assert.equal(resolveAvatarSrc("https://plex.test/a.jpg"), "https://plex.test/a.jpg");
  });

  it("keeps local API paths absolute from site root", () => {
    assert.equal(resolveAvatarSrc("/api/auth/avatar/plex-1"), "/api/auth/avatar/plex-1");
  });

  it("adds cache bust query when provided", () => {
    assert.equal(
      resolveAvatarSrc("/api/auth/avatar/plex-1", "123"),
      "/api/auth/avatar/plex-1?v=123",
    );
  });

  it("returns empty for missing avatars", () => {
    assert.equal(resolveAvatarSrc(""), "");
    assert.equal(resolveAvatarSrc(null), "");
  });
});

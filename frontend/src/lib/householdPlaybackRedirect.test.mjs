import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { householdPlaybackRedirect } from "./householdPlaybackRedirect.ts";

describe("householdPlaybackRedirect", () => {
  it("sends the old Profile playback anchor to Household → Playback", () => {
    assert.equal(
      householdPlaybackRedirect("/settings/profile", "#playback"),
      "/admin/playback",
    );
    assert.equal(
      householdPlaybackRedirect("/settings/profile/", "#PLAYBACK"),
      "/admin/playback",
    );
    assert.equal(
      householdPlaybackRedirect("/settings/profile", "#play-through-projectionist"),
      "/admin/playback#play-through-projectionist",
    );
    assert.equal(
      householdPlaybackRedirect("/settings/profile", "#away-address"),
      "/admin/playback#away-address",
    );
    assert.equal(
      householdPlaybackRedirect("/settings/profile", "#playability"),
      "/admin/playback#playability",
    );
    assert.equal(
      householdPlaybackRedirect("/settings/profile", "#copies"),
      "/admin/playback#copies",
    );
  });

  it("sends retired playback routes to the admin section", () => {
    assert.equal(householdPlaybackRedirect("/settings/playback", ""), "/admin/playback");
    assert.equal(
      householdPlaybackRedirect("/settings/profile/playback", "#ignored"),
      "/admin/playback",
    );
  });

  it("leaves personal Profile anchors where they are", () => {
    assert.equal(householdPlaybackRedirect("/settings/profile", ""), null);
    assert.equal(householdPlaybackRedirect("/settings/profile", "#badges"), null);
    assert.equal(householdPlaybackRedirect("/settings/profile", "#font-size"), null);
    assert.equal(householdPlaybackRedirect("/settings", "#playback"), null);
    assert.equal(householdPlaybackRedirect("/admin/playback", "#playback"), null);
  });

  it("ignores hostile or oversized hashes", () => {
    assert.equal(
      householdPlaybackRedirect("/settings/profile", "#<script>alert(1)</script>"),
      null,
    );
    assert.equal(
      householdPlaybackRedirect("/settings/profile", `#${"playback".repeat(20)}`),
      null,
    );
    assert.equal(householdPlaybackRedirect("/settings/profile", "#playback%00"), null);
    assert.equal(householdPlaybackRedirect("", "#playback"), null);
  });
});

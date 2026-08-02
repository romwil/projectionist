import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  buildCraftFiltersPayload,
  craftDraftFromStation,
} from "./liveChannelsCraft.js";

describe("liveChannelsCraft", () => {
  it("round-trips decade/genre craft filters for station Settings", () => {
    const draft = craftDraftFromStation({
      media_scope: "movies",
      subtitles_enabled: true,
      source: "motif",
      motif: "creature feature",
      craft_filters: {
        genres: ["Horror"],
        decade: 1970,
        year_from: 1970,
        year_to: 1979,
        themes: ["creature feature"],
      },
    });
    assert.equal(draft.media_scope, "movies");
    assert.equal(draft.motif, "creature feature");
    assert.equal(draft.decade, "1970");
    assert.deepEqual(draft.genres, ["Horror"]);
    assert.equal(draft.theme, "creature feature");

    const payload = buildCraftFiltersPayload(draft);
    assert.equal(payload.decade, 1970);
    assert.deepEqual(payload.genres, ["Horror"]);
    assert.deepEqual(payload.themes, ["creature feature"]);
  });

  it("clears filters when Settings selects Any", () => {
    const payload = buildCraftFiltersPayload({
      genres: [],
      decade: "",
      theme: "",
      content_rating: "",
    });
    assert.deepEqual(payload, {});
  });
});

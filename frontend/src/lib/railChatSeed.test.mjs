import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  buildRailChatPrompt,
  compactRailItem,
  decodeRailPack,
  encodeRailPack,
  expandRailItem,
  mergeRailSeedCards,
  railItemsToTitleCards,
} from "./railChatSeed.js";

describe("railChatSeed", () => {
  it("compacts and expands stable ids + why", () => {
    const compact = compactRailItem({
      id: 42,
      title: "Heat",
      year: 1995,
      media_type: "movie",
      rating_key: "rk-heat",
      why: "Fits your noir lean",
      tmdb_id: 949,
    });
    assert.equal(compact.t, "Heat");
    assert.equal(compact.id, 42);
    assert.equal(compact.rk, "rk-heat");
    assert.equal(compact.w, "Fits your noir lean");
    const expanded = expandRailItem(compact);
    assert.equal(expanded.title, "Heat");
    assert.equal(expanded.rating_key, "rk-heat");
    assert.equal(expanded.recommendation_reason, "Fits your noir lean");
    assert.equal(expanded.in_library, true);
  });

  it("round-trips rail_pack encoding", () => {
    const pack = encodeRailPack([
      { id: 1, title: "Heat", year: 1995, media_type: "movie", rating_key: "rk-1", why: "Noir lean" },
      { id: 2, title: "Arrival", year: 2016, media_type: "movie", rating_key: "rk-2", why: "Sci-fi lean" },
    ]);
    assert.ok(pack);
    const items = decodeRailPack(pack);
    assert.equal(items.length, 2);
    assert.equal(items[0].title, "Heat");
    assert.equal(items[0].rating_key, "rk-1");
    assert.equal(items[1].why, "Sci-fi lean");
  });

  it("builds a prompt with library ids and why, forbidding TMDB replacements", () => {
    const prompt = buildRailChatPrompt({
      railTitle: "For you this week",
      items: [
        {
          id: 7,
          title: "Heat",
          year: 1995,
          media_type: "movie",
          rating_key: "rk-heat",
          why: "Fits your noir lean",
        },
      ],
    });
    assert.match(prompt, /library_id=7/);
    assert.match(prompt, /rating_key=rk-heat/);
    assert.match(prompt, /noir lean/);
    assert.match(prompt, /Do NOT search TMDB/);
  });

  it("merges seed cards over external Add posters", () => {
    const seed = railItemsToTitleCards([
      {
        id: 7,
        title: "Heat",
        year: 1995,
        media_type: "movie",
        rating_key: "rk-heat",
        why: "Fits your noir lean",
        poster_url: "/p/heat.jpg",
      },
    ]);
    const merged = mergeRailSeedCards(
      {
        role: "assistant",
        blocks: [
          { type: "text", content: "Here are some picks." },
          {
            type: "title_cards",
            items: [{ title: "Some Other Heat", media_type: "movie", tmdb_id: 1, in_library: false }],
          },
        ],
      },
      seed,
    );
    const cards = merged.blocks.find((b) => b.type === "title_cards").items;
    assert.equal(cards.length, 1);
    assert.equal(cards[0].title, "Heat");
    assert.equal(cards[0].in_library, true);
    assert.equal(cards[0].recommendation_reason, "Fits your noir lean");
  });
});

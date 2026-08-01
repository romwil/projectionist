import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  SAVED_LIBRARY_RAIL_LIMIT,
  sanitizeSavedRailItems,
  savedLibraryBlocks,
} from "./savedLibraryBlocks.js";

const SEVEN_MOVIES = Array.from({ length: 7 }, (_, i) => ({
  media_type: "movie",
  tmdb_id: 100 + i,
  title: `Movie ${i}`,
}));

describe("savedLibraryBlocks", () => {
  it("renders intro text, title cards, and suggested replies in order and does not blank out when an open_viewport action block is present", () => {
    const blocks = [
      { type: "text", content: "Here are the results I found." },
      { type: "title_cards", items: SEVEN_MOVIES },
      {
        type: "action_prompt",
        action: "open_viewport",
        payload: { title: "Recommendations", items: SEVEN_MOVIES },
      },
      { type: "suggested_replies", payload: { replies: ["More like this", "Something lighter"] } },
    ];

    const rendered = savedLibraryBlocks(blocks);

    assert.deepEqual(
      rendered.map((b) => b.kind),
      ["text", "title_cards", "suggested_replies"],
    );
    assert.equal(rendered[0].content, "Here are the results I found.");
    assert.equal(rendered[1].items.length, 7);
    assert.deepEqual(rendered[2].replies, ["More like this", "Something lighter"]);
  });

  it("does not auto-open or duplicate cards: open_viewport is dropped when a title_cards block already shows the items", () => {
    const blocks = [
      { type: "title_cards", items: SEVEN_MOVIES },
      { type: "action_prompt", action: "open_viewport", payload: { items: SEVEN_MOVIES } },
    ];

    const rendered = savedLibraryBlocks(blocks);
    const cardBlocks = rendered.filter(
      (b) => b.kind === "title_cards" || b.kind === "recommendations",
    );
    assert.equal(cardBlocks.length, 1);
    assert.equal(cardBlocks[0].kind, "title_cards");
  });

  it("renders an inert recommendations grid when open_viewport has no sibling title_cards", () => {
    const blocks = [
      { type: "text", content: "Curated picks" },
      {
        type: "action_prompt",
        action: "open_viewport",
        payload: { title: "Recommendations", items: SEVEN_MOVIES },
      },
    ];

    const rendered = savedLibraryBlocks(blocks);
    assert.deepEqual(rendered.map((b) => b.kind), ["text", "recommendations"]);
    assert.equal(rendered[1].items.length, 7);
    assert.equal(rendered[1].title, "Recommendations");
  });

  it("skips empty/whitespace text and unknown blocks instead of emitting blank nodes", () => {
    const blocks = [
      { type: "text", content: "   " },
      { type: "action_prompt", action: "open_viewport", payload: { items: [] } },
      { type: "double_feature", payload: { title_a: {}, title_b: {} } },
      { type: "text", content: "Real text" },
      null,
    ];

    const rendered = savedLibraryBlocks(blocks);
    assert.deepEqual(rendered.map((b) => b.kind), ["text"]);
    assert.equal(rendered[0].content, "Real text");
  });

  it("caps suggested replies at four and drops falsy entries", () => {
    const blocks = [
      {
        type: "suggested_replies",
        payload: { replies: ["a", "", "b", null, "c", "d", "e"] },
      },
    ];
    const rendered = savedLibraryBlocks(blocks);
    assert.deepEqual(rendered[0].replies, ["a", "b", "c", "d"]);
  });

  it("keeps persona_consult quote blocks for saved pages", () => {
    const blocks = [
      {
        type: "persona_consult",
        payload: {
          persona: "Scholar",
          lead: "I asked Scholar and they said",
          answer: "Two cited neighbors.",
          specialty: "citations",
        },
      },
    ];
    const rendered = savedLibraryBlocks(blocks);
    assert.equal(rendered.length, 1);
    assert.equal(rendered[0].kind, "persona_consult");
    assert.equal(rendered[0].persona, "Scholar");
    assert.equal(rendered[0].answer, "Two cited neighbors.");
  });

  it("returns an empty list for missing/invalid input", () => {
    assert.deepEqual(savedLibraryBlocks(), []);
    assert.deepEqual(savedLibraryBlocks(null), []);
    assert.deepEqual(savedLibraryBlocks("nope"), []);
  });

  it("sanitizeSavedRailItems drops id-less cards, de-dupes, and caps length", () => {
    const items = [
      { media_type: "show", title: "Chernobyl", tmdb_id: 87108 },
      { media_type: "show", title: "Chernobyl copy", tmdb_id: 87108 },
      { media_type: "show", title: "Invented", tmdb_id: 0 },
      { media_type: "show", title: "", tmdb_id: 12 },
      ...Array.from({ length: 20 }, (_, i) => ({
        media_type: "show",
        title: `Extra ${i}`,
        tmdb_id: 2000 + i,
      })),
    ];
    const cleaned = sanitizeSavedRailItems(items);
    assert.equal(cleaned.length, SAVED_LIBRARY_RAIL_LIMIT);
    assert.equal(cleaned[0].title, "Chernobyl");
    assert.equal(cleaned.filter((c) => c.tmdb_id === 87108).length, 1);
    assert.ok(cleaned.every((c) => c.tmdb_id > 0 && String(c.title || "").trim()));
  });

  it("savedLibraryBlocks hardens crazy title_cards rails from bad gap saves", () => {
    const crazy = Array.from({ length: 40 }, (_, i) => ({
      media_type: "show",
      title: i % 3 === 0 ? "" : `Gap ${i}`,
      tmdb_id: i % 5 === 0 ? 0 : 5000 + (i % 7),
    }));
    const rendered = savedLibraryBlocks([{ type: "title_cards", items: crazy }]);
    assert.equal(rendered.length, 1);
    assert.ok(rendered[0].items.length <= SAVED_LIBRARY_RAIL_LIMIT);
    assert.ok(rendered[0].items.every((c) => c.tmdb_id > 0 && c.title));
  });
});

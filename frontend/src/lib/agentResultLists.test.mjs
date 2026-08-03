import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  buildAgentRailPrompt,
  lastMarkdownHeading,
  materializeAgentResultList,
  pageAgentListItems,
} from "./agentResultLists.js";

const RESULTS = [
  { title: "Heat", year: 1995, media_type: "movie", tmdb_id: 949, library_item_id: 7 },
  { title: "The Bear", year: 2022, media_type: "show", tvdb_id: 393589 },
  { title: "No stable identity", media_type: "movie" },
];

describe("agent result list actions", () => {
  it("uses the last markdown heading before a media list", () => {
    assert.equal(
      lastMarkdownHeading("A few thoughts.\n\n## Tonight's tense picks\n\nThese all fit."),
      "Tonight's tense picks",
    );
    assert.equal(lastMarkdownHeading("No heading here."), "");
  });

  it("builds a rail-creation prompt with exact result identities", () => {
    const prompt = buildAgentRailPrompt({
      heading: "Tonight's tense picks",
      items: RESULTS,
    });
    assert.match(prompt, /curated list rail/i);
    assert.match(prompt, /Heat \(1995\).*tmdb_id=949/);
    assert.match(prompt, /The Bear \(2022\).*tvdb_id=393589/);
    assert.doesNotMatch(prompt, /No stable identity/);
  });

  it("materializes one saved list and adds only stable media identities", async () => {
    const calls = [];
    const result = await materializeAgentResultList({
      heading: "Tonight's tense picks",
      items: RESULTS,
      createList: async (payload) => {
        calls.push(["create", payload]);
        return { id: "list-123", ...payload };
      },
      addItem: async (listId, payload) => {
        calls.push(["add", listId, payload]);
        return payload;
      },
      now: new Date("2026-08-03T02:00:00Z"),
    });

    assert.equal(result.list.id, "list-123");
    assert.equal(result.added, 2);
    assert.equal(result.skipped, 1);
    assert.equal(calls[0][1].list_kind, "list");
    assert.match(calls[0][1].description, /agent result/i);
    assert.deepEqual(calls[1][2], {
      title: "Heat",
      media_type: "movie",
      tmdb_id: 949,
      tvdb_id: undefined,
      library_item_id: 7,
    });
  });

  it("paginates a filtered list without mutating its order", () => {
    const items = Array.from({ length: 55 }, (_, index) => ({ title: `Title ${index + 1}` }));
    const page = pageAgentListItems(items, { limit: 48, offset: 48 });
    assert.equal(page.items.length, 7);
    assert.equal(page.total, 55);
    assert.equal(page.hasPrevious, true);
    assert.equal(page.hasNext, false);
    assert.equal(items[0].title, "Title 1");
  });
});

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  GENERIC_RESULTS_PLACEHOLDER,
  mergeStreamedBlocks,
} from "./mergeStreamedBlocks.js";

const SEVEN_MOVIES = Array.from({ length: 7 }, (_, i) => ({
  media_type: "movie",
  tmdb_id: 100 + i,
  title: `Movie ${i}`,
}));

describe("mergeStreamedBlocks", () => {
  it("keeps streamed prose and appends backend cards when backend text is the generic placeholder", () => {
    const backend = {
      id: "abc",
      role: "assistant",
      blocks: [
        { type: "text", content: GENERIC_RESULTS_PLACEHOLDER },
        { type: "title_cards", items: SEVEN_MOVIES },
        {
          type: "action_prompt",
          action: "open_viewport",
          payload: { title: "Results", items: SEVEN_MOVIES },
        },
        { type: "suggested_replies", payload: { replies: ["More like this"] } },
      ],
    };
    const streamed = "Let me dig through your library for cozy sci-fi. Here's what stood out.";

    const merged = mergeStreamedBlocks(backend, streamed);

    assert.equal(merged.blocks[0].type, "text");
    assert.equal(merged.blocks[0].content, streamed);
    assert.deepEqual(
      merged.blocks.map((b) => b.type),
      ["text", "title_cards", "action_prompt", "suggested_replies"],
    );
    // Non-text blocks are preserved unchanged.
    assert.equal(merged.blocks[1].items.length, 7);
    assert.equal(merged.id, "abc");
  });

  it("keeps streamed prose when the backend leading text block is empty", () => {
    const backend = {
      blocks: [
        { type: "text", content: "   " },
        { type: "title_cards", items: SEVEN_MOVIES },
      ],
    };
    const streamed = "Here are three picks I think you'll love.";

    const merged = mergeStreamedBlocks(backend, streamed);

    assert.equal(merged.blocks[0].content, streamed);
    assert.deepEqual(merged.blocks.map((b) => b.type), ["text", "title_cards"]);
  });

  it("uses backend blocks as-is when backend text is real prose", () => {
    const backend = {
      blocks: [
        { type: "text", content: "A full, detailed backend reply about your picks." },
        { type: "title_cards", items: SEVEN_MOVIES },
      ],
    };
    const streamed = "A full, detailed backend reply about your picks.";

    const merged = mergeStreamedBlocks(backend, streamed);

    assert.equal(merged, backend);
    assert.equal(merged.blocks[0].content, "A full, detailed backend reply about your picks.");
  });

  it("returns the backend message unchanged when there is no streamed prose", () => {
    const backend = { blocks: [{ type: "text", content: GENERIC_RESULTS_PLACEHOLDER }] };
    assert.equal(mergeStreamedBlocks(backend, ""), backend);
    assert.equal(mergeStreamedBlocks(backend, "   "), backend);
    assert.equal(mergeStreamedBlocks(backend, undefined), backend);
  });

  it("returns the input untouched for missing/invalid messages", () => {
    assert.equal(mergeStreamedBlocks(null, "prose"), null);
    assert.equal(mergeStreamedBlocks(undefined, "prose"), undefined);
  });
});

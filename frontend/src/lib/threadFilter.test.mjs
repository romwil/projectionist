import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { filterThreads } from "./threadFilter.js";

describe("threadFilter", () => {
  it("filters by title or preview", () => {
    const threads = [
      { id: "1", thread_title: "Sci-fi night", preview: "Aliens" },
      { id: "2", thread_title: "Comedy", preview: "something funny" },
    ];
    assert.equal(filterThreads(threads, "sci").length, 1);
    assert.equal(filterThreads(threads, "funny")[0].id, "2");
    assert.equal(filterThreads(threads, "").length, 2);
  });
});

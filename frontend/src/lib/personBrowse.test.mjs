import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  creditRoleBucket,
  filterPersonTitles,
  libraryOwnedPercent,
} from "./personBrowse.js";

describe("personBrowse", () => {
  it("buckets director vs cast credits", () => {
    assert.equal(creditRoleBucket({ job: "Director", department: "Directing" }), "director");
    assert.equal(creditRoleBucket({ character: "Deckard", department: "Acting" }), "cast");
  });

  it("filters titles by role", () => {
    const titles = [
      { title: "A", job: "Director", department: "Directing" },
      { title: "B", character: "Hero", department: "Acting" },
    ];
    assert.equal(filterPersonTitles(titles, "director").length, 1);
    assert.equal(filterPersonTitles(titles, "cast")[0].title, "B");
    assert.equal(filterPersonTitles(titles, "all").length, 2);
  });

  it("computes owned percent when filmography total exists", () => {
    assert.deepEqual(libraryOwnedPercent({ in_library_count: 5, filmography_total: 20 }), {
      owned: 5,
      total: 20,
      pct: 25,
      label: "25% of filmography in library",
    });
    assert.equal(libraryOwnedPercent({ in_library_count: 5 }), null);
  });
});

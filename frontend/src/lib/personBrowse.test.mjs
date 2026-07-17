import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  creditRoleBucket,
  filterPersonTitles,
  groupPersonTitles,
  libraryOwnedPercent,
  personTitleKey,
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

  it("collapses repeated media pieces into one entry with aggregated credits", () => {
    const titles = [
      { media_type: "movie", tmdb_id: 7446, title: "Tropic Thunder", year: 2008, character: "Tugg Speedman" },
      { media_type: "movie", tmdb_id: 7446, title: "Tropic Thunder", job: "Director" },
      { media_type: "movie", tmdb_id: 7446, title: "Tropic Thunder", job: "Producer", poster_url: "/p.jpg" },
      { media_type: "movie", tmdb_id: 7446, title: "Tropic Thunder", job: "Director" },
      { media_type: "movie", tmdb_id: 550, title: "Fight Club", character: "Narrator" },
    ];
    const grouped = groupPersonTitles(titles);
    assert.equal(grouped.length, 2);
    const thunder = grouped[0];
    assert.equal(thunder.title, "Tropic Thunder");
    assert.deepEqual(thunder.credits, ["Tugg Speedman", "Director", "Producer"]);
    assert.equal(thunder.poster_url, "/p.jpg");
    assert.equal(grouped[1].credits[0], "Narrator");
  });

  it("keys media by tmdb id, rating key, then title/year", () => {
    assert.equal(personTitleKey({ media_type: "movie", tmdb_id: 7446 }), "movie:tmdb:7446");
    assert.equal(personTitleKey({ media_type: "show", rating_key: "abc" }), "show:rk:abc");
    assert.equal(
      personTitleKey({ media_type: "movie", title: "Solaris", year: 1972 }),
      "movie:title:solaris:1972",
    );
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

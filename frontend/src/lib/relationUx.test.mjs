import test from "node:test";
import assert from "node:assert/strict";

import {
  appendRelationBreadcrumb,
  filterRelationEdges,
  relationWhyCopy,
  relatedTitlesPath,
} from "./relationUx.js";

test("appendRelationBreadcrumb keeps a two-hop trail without duplicate seeds", () => {
  const seed = { library_item_id: 1, title: "Seed" };
  const firstHop = { library_item_id: 2, title: "First hop" };

  assert.deepEqual(appendRelationBreadcrumb([], seed), [seed]);
  assert.deepEqual(appendRelationBreadcrumb([seed], seed), [seed]);
  assert.deepEqual(appendRelationBreadcrumb([seed], firstHop), [seed, firstHop]);
});

test("relationWhyCopy keeps the plain why first and surprise context second", () => {
  assert.deepEqual(
    relationWhyCopy({
      label: "Strong plot kinship · Shared genres: Drama",
      surprise_flavor: "Shelf labels barely overlap",
    }),
    {
      label: "Strong plot kinship · Shared genres: Drama",
      detail: "Surprising because shelf labels barely overlap.",
    },
  );
});

test("relationWhyCopy surfaces shared genres when the main label does not", () => {
  assert.deepEqual(
    relationWhyCopy({
      label: "Same collection: Future Stories",
      shared_genres: ["Drama", "Science Fiction"],
    }),
    {
      label: "Same collection: Future Stories",
      detail: "Shared genres: Drama, Science Fiction.",
    },
  );
});

test("filterRelationEdges supports relation types and surprising similarity", () => {
  const edges = [
    { relation: "collection", why: { label: "Same collection" } },
    { relation: "shared_crew", why: { label: "Shared crew" } },
    { relation: "neighbor", why: { label: "Plot kinship", surprise_flavor: null } },
    {
      relation: "neighbor",
      why: { label: "Plot kinship", surprise_flavor: "Almost no shared labels" },
    },
  ];

  assert.equal(filterRelationEdges(edges, "all").length, 4);
  assert.equal(filterRelationEdges(edges, "shared_crew").length, 1);
  assert.equal(filterRelationEdges(edges, "surprising").length, 1);
});

test("relatedTitlesPath chooses a stable title id and preserves seed copy", () => {
  assert.equal(
    relatedTitlesPath({
      media_type: "movie",
      tmdb_id: 101,
      title: "Seed & Stone",
      year: 2020,
    }),
    "/explore/related?media_type=movie&item_id=101&id_type=tmdb&title=Seed+%26+Stone&year=2020",
  );
});

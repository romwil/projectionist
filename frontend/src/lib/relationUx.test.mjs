import test from "node:test";
import assert from "node:assert/strict";

import {
  appendRelationBreadcrumb,
  filterRelationEdges,
  isSurprisingRelation,
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

test("relationWhyCopy leads with a named story link and keeps shelf distance second", () => {
  assert.deepEqual(
    relationWhyCopy({
      label: "Strong plot kinship",
      plot_link: "Both stories turn on amateur bakers.",
      shelf_note: "Shelf labels barely overlap",
      surprise_flavor: "Both stories turn on amateur bakers.",
    }),
    {
      label: "Both stories turn on amateur bakers.",
      detail: "Shelf labels barely overlap.",
    },
  );
});

test("relationWhyCopy does not recommend a title for having no shared labels", () => {
  assert.deepEqual(
    relationWhyCopy({
      label: "Strong plot kinship",
      surprise_flavor: "Almost no shared genre, keyword, or credit labels",
    }),
    {
      label: "Strong plot kinship",
      detail: "",
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
      why: {
        label: "Strong plot kinship",
        surprise_flavor: "Almost no shared labels",
      },
    },
    {
      relation: "neighbor",
      why: {
        label: "Both stories turn on amateur bakers.",
        plot_link: "Both stories turn on amateur bakers.",
      },
    },
  ];

  assert.equal(filterRelationEdges(edges, "all").length, 5);
  assert.equal(filterRelationEdges(edges, "shared_crew").length, 1);
  assert.equal(filterRelationEdges(edges, "surprising").length, 1);
  assert.equal(isSurprisingRelation(edges[3]), false);
  assert.equal(isSurprisingRelation(edges[4]), true);
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

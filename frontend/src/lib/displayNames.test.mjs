import assert from "node:assert/strict";
import test from "node:test";

import {
  knowledgeEventDisplayName,
  knowledgeGapDisplayName,
  knowledgeTaskDisplayName,
} from "./knowledgeOpsDisplay.js";
import {
  actDescriptionForStagedItem,
  actLabelForStagedItem,
} from "./knowledgeOpsActions.js";
import { taskDisplayName } from "./scheduledTasks.js";

test("scheduled task ids keep plain owner-facing names", () => {
  assert.equal(taskDisplayName("semantic_embeddings"), "Plot similarity index");
  assert.equal(
    taskDisplayName("facet_taxonomy_audit"),
    "Review unrecognized genre/tag names",
  );
  assert.equal(taskDisplayName("coverage_deficit_audit"), "Find missing plot knowledge");
  assert.equal(taskDisplayName("title_relations_refresh"), "Refresh title connections");
});

test("knowledge activity maps internal event and task ids", () => {
  assert.equal(knowledgeEventDisplayName("bad_neighbor_match"), "Marked not similar");
  assert.equal(
    knowledgeTaskDisplayName("entity_memory_enrichment"),
    "Research missing title details",
  );
  assert.equal(knowledgeGapDisplayName("theme_keyword"), "Themes from tags");
});

test("knowledge actions describe outcomes without backend jargon", () => {
  const facet = {
    task_name: "facet_taxonomy_audit",
    target_entity_type: "facet",
    candidate: { alias: "sci fi" },
  };
  assert.equal(actLabelForStagedItem(facet), "Save mapping");

  const memory = {
    task_name: "entity_memory_enrichment",
    candidate: { name: "Heat" },
  };
  assert.equal(
    actDescriptionForStagedItem(memory),
    "Refresh trusted title details for “Heat”.",
  );

  const motif = {
    task_name: "coverage_deficit_audit",
    candidate: { name: "Heat", deficit_kind: "motif" },
  };
  assert.equal(
    actDescriptionForStagedItem(motif),
    "Find plot patterns in the available summary for “Heat”.",
  );
});

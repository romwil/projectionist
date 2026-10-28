import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { embeddingCoverageLabel } from "./knowledgeCoverage.ts";

const root = dirname(fileURLToPath(import.meta.url));

test("Explore For you is the first rail and there is only one For you", () => {
  const page = readFileSync(join(root, "../pages/ExplorePage.jsx"), "utf8");
  const forYou = page.indexOf('id="for-you"');
  const continueWatching = page.indexOf('id="continue-watching"');
  assert.ok(forYou > 0, "For you rail missing");
  assert.ok(continueWatching > 0, "Continue Watching rail missing");
  assert.ok(forYou < continueWatching, "For you must be the first Explore rail");
  assert.equal((page.match(/id="for-you"/g) || []).length, 1);
  assert.doesNotMatch(page, /For you this week/);
  assert.doesNotMatch(page, /weekly-for-you/);
});

test("hash-fallback is labeled on coverage strip and Admin panel", () => {
  const card = readFileSync(join(root, "../components/KnowledgeCoverageCard.jsx"), "utf8");
  const explore = readFileSync(join(root, "../pages/ExplorePage.jsx"), "utf8");
  const knowledgeOps = readFileSync(join(root, "../pages/StagedAugmentationsPage.jsx"), "utf8");
  assert.match(card, /variant === "strip"/);
  assert.match(card, /embeddingCoverageLabel/);
  assert.match(card, /knowledge-coverage-embedding/);
  assert.match(explore, /KnowledgeCoverageCard variant="strip"/);
  assert.match(knowledgeOps, /embeddingCoverageLabel/);
  assert.match(knowledgeOps, /knowledge-ops-coverage-embedding/);
  assert.equal(
    embeddingCoverageLabel({ embedding_is_hash_fallback: true, embedding_model: "hash-fallback" }),
    "Vectors: local hash embeddings (no embedding API)",
  );
});

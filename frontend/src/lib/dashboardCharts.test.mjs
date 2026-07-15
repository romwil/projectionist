import assert from "node:assert/strict";
import test from "node:test";

import { buildRuntimeBuckets, sortPurgeCandidates } from "./dashboardCharts.js";

// ── buildRuntimeBuckets ──

test("buildRuntimeBuckets returns empty array for null/empty input", () => {
  assert.deepEqual(buildRuntimeBuckets(null), []);
  assert.deepEqual(buildRuntimeBuckets([]), []);
  assert.deepEqual(buildRuntimeBuckets(undefined), []);
});

test("buildRuntimeBuckets groups labeled buckets in canonical order", () => {
  const input = [
    { label: "Epic (150m+)", count: 5 },
    { label: "Short (<90m)", count: 20 },
    { label: "Medium (90–120m)", count: 30 },
    { label: "Long (120–150m)", count: 12 },
  ];
  const result = buildRuntimeBuckets(input);
  assert.equal(result.length, 4);
  assert.equal(result[0].label, "Short (<90m)");
  assert.equal(result[0].value, 20);
  assert.equal(result[1].label, "Medium (90–120m)");
  assert.equal(result[1].value, 30);
  assert.equal(result[2].label, "Long (120–150m)");
  assert.equal(result[2].value, 12);
  assert.equal(result[3].label, "Epic (150m+)");
  assert.equal(result[3].value, 5);
});

test("buildRuntimeBuckets omits buckets with zero count", () => {
  const input = [
    { label: "Short (<90m)", count: 10 },
    { label: "Epic (150m+)", count: 3 },
  ];
  const result = buildRuntimeBuckets(input);
  assert.equal(result.length, 2);
  assert.equal(result[0].label, "Short (<90m)");
  assert.equal(result[1].label, "Epic (150m+)");
});

// ── sortPurgeCandidates ──

test("sortPurgeCandidates returns empty for null/empty", () => {
  assert.deepEqual(sortPurgeCandidates(null, "title", "asc"), []);
  assert.deepEqual(sortPurgeCandidates([], "title", "asc"), []);
});

test("sortPurgeCandidates sorts by string field ascending", () => {
  const input = [
    { title: "Zulu", purge_score: 5 },
    { title: "Alpha", purge_score: 8 },
    { title: "Middle", purge_score: 3 },
  ];
  const result = sortPurgeCandidates(input, "title", "asc");
  assert.equal(result[0].title, "Alpha");
  assert.equal(result[1].title, "Middle");
  assert.equal(result[2].title, "Zulu");
});

test("sortPurgeCandidates sorts by numeric field descending", () => {
  const input = [
    { title: "A", purge_score: 2.1 },
    { title: "B", purge_score: 9.5 },
    { title: "C", purge_score: 5.0 },
  ];
  const result = sortPurgeCandidates(input, "purge_score", "desc");
  assert.equal(result[0].purge_score, 9.5);
  assert.equal(result[1].purge_score, 5.0);
  assert.equal(result[2].purge_score, 2.1);
});

test("sortPurgeCandidates does not mutate original array", () => {
  const input = [
    { title: "B", purge_score: 1 },
    { title: "A", purge_score: 2 },
  ];
  const result = sortPurgeCandidates(input, "title", "asc");
  assert.equal(input[0].title, "B");
  assert.equal(result[0].title, "A");
  assert.notEqual(input, result);
});

test("sortPurgeCandidates handles case-insensitive string comparison", () => {
  const input = [
    { title: "banana", purge_score: 1 },
    { title: "Apple", purge_score: 2 },
  ];
  const result = sortPurgeCandidates(input, "title", "asc");
  assert.equal(result[0].title, "Apple");
  assert.equal(result[1].title, "banana");
});

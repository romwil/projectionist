import assert from "node:assert/strict";
import test from "node:test";
import { createSlugger, slugify, targetIdFromHash } from "./helpAnchors.js";

test("slugify matches the Help anchors used across the app", () => {
  assert.equal(slugify("Start here"), "start-here");
  assert.equal(slugify("Chat"), "chat");
  assert.equal(slugify("Related titles"), "related-titles");
  assert.equal(slugify("Tags"), "tags");
  assert.equal(slugify("Coverage over time"), "coverage-over-time");
  assert.equal(
    slugify("Refreshing plot patterns after an update"),
    "refreshing-plot-patterns-after-an-update",
  );
  assert.equal(slugify("Telemetry & tuning"), "telemetry--tuning");
  assert.equal(slugify("LLM vs free sources"), "llm-vs-free-sources");
  assert.equal(slugify("What knowledge coverage means"), "what-knowledge-coverage-means");
});

test("slugify reproduces GitHub's em-dash / ampersand double hyphens", () => {
  assert.equal(slugify("For owners — curation & scheduler"), "for-owners--curation--scheduler");
  assert.equal(slugify("Title detail — Plot knowledge"), "title-detail--plot-knowledge");
  assert.equal(slugify("For everyone — browse & chat"), "for-everyone--browse--chat");
});

test("slugify is defensive about empty / nullish input", () => {
  assert.equal(slugify(""), "");
  assert.equal(slugify(null), "");
  assert.equal(slugify(undefined), "");
});

test("targetIdFromHash decodes the anchor to a scrollable element id", () => {
  assert.equal(targetIdFromHash("#coverage-over-time"), "coverage-over-time");
  assert.equal(targetIdFromHash("coverage-over-time"), "coverage-over-time");
  assert.equal(targetIdFromHash("#what%20knowledge"), "what knowledge");
  assert.equal(targetIdFromHash("#  spaced  "), "spaced");
  assert.equal(targetIdFromHash(""), "");
  assert.equal(targetIdFromHash("#"), "");
  assert.equal(targetIdFromHash(null), "");
  assert.equal(targetIdFromHash(undefined), "");
});

test("createSlugger de-duplicates repeated headings", () => {
  const slug = createSlugger();
  assert.equal(slug("Overview"), "overview");
  assert.equal(slug("Overview"), "overview-1");
  assert.equal(slug("Overview"), "overview-2");
  assert.equal(slug("Chat"), "chat");
});

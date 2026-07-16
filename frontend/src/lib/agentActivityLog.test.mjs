import assert from "node:assert/strict";
import test from "node:test";

import {
  activityEventFromToolCall,
  appendActivityLog,
  createActivityEvent,
  formatToolArgs,
  nextActivityPanelExpanded,
  summarizeToolResult,
  truncateText,
} from "./agentActivityLog.js";

test("truncateText shortens long strings with ellipsis", () => {
  assert.equal(truncateText("short"), "short");
  assert.equal(truncateText(""), "");
  const long = "x".repeat(200);
  const out = truncateText(long, 20);
  assert.equal(out.length, 20);
  assert.ok(out.endsWith("..."));
});

test("formatToolArgs prefers compact key=value and truncates", () => {
  assert.equal(formatToolArgs(null), "");
  assert.equal(formatToolArgs({ query: "noir", year: 1974 }), "query=noir, year=1974");
  assert.equal(formatToolArgs("already a string"), "already a string");
  const huge = formatToolArgs({ blob: "y".repeat(400) });
  assert.ok(huge.length <= 160);
  assert.ok(huge.startsWith("blob="));
});

test("summarizeToolResult truncates JSON and strings", () => {
  assert.equal(summarizeToolResult(""), "");
  assert.equal(summarizeToolResult({ ok: true }), '{"ok":true}');
  assert.ok(summarizeToolResult("z".repeat(300)).endsWith("..."));
});

test("activityEventFromToolCall maps start and complete", () => {
  const start = activityEventFromToolCall({
    name: "search_library",
    status: "start",
    args: { query: "noir" },
  });
  assert.equal(start.kind, "tool_start");
  assert.equal(start.label, "search library");
  assert.equal(start.detail, "query=noir");

  const done = activityEventFromToolCall({
    name: "search_library",
    status: "complete",
    summary: '[{"title":"Chinatown"}]',
  });
  assert.equal(done.kind, "tool_result");
  assert.match(done.label, /done/);
  assert.match(done.detail, /Chinatown/);
});

test("appendActivityLog appends and caps length", () => {
  let log = [];
  log = appendActivityLog(log, createActivityEvent({ kind: "status", label: "Thinking" }));
  log = appendActivityLog(log, createActivityEvent({ kind: "token_note", label: "Writing response…" }));
  assert.equal(log.length, 2);
  assert.equal(log[0].kind, "status");

  const seeded = Array.from({ length: 5 }, (_, i) =>
    createActivityEvent({ kind: "status", label: `n${i}`, t: i }),
  );
  const capped = appendActivityLog(seeded, createActivityEvent({ kind: "status", label: "tail", t: 99 }), {
    maxEntries: 3,
  });
  assert.equal(capped.length, 3);
  assert.equal(capped[2].label, "tail");
  assert.equal(capped[0].label, "n3");
});

test("nextActivityPanelExpanded collapses on stream done", () => {
  assert.equal(nextActivityPanelExpanded({ streamDone: true, expanded: true }), false);
  assert.equal(nextActivityPanelExpanded({ streamDone: false, expanded: true }), true);
  assert.equal(nextActivityPanelExpanded({ streamDone: false, expanded: false }), false);
});

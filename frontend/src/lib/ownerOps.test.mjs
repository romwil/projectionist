import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  CATCHUP_SHORTLIST_LIMIT,
  auditDetailLine,
  auditEventLabel,
  checklistProgress,
  formatLastProbe,
  resolveTaskView,
  secretStateCopy,
  summarizeNeedsAttention,
  taskCatchupShortlist,
} from "./ownerOps.ts";

function task(name, extra = {}) {
  return { name, enabled: true, last_status: "completed", ...extra };
}

describe("taskCatchupShortlist", () => {
  it("puts failed and quarantined first, then Warm Explore, then overdue", () => {
    const items = [
      task("taste_refresh"),
      task("summary_motifs"),
      task("gap_analysis", { overdue: true }),
      task("data_retention", { quarantine: { is_quarantined: true } }),
      task("metadata_enrichment"),
      task("anniversary_scanner", { last_status: "error: boom" }),
    ];
    const names = taskCatchupShortlist(items).map((t) => t.name);
    assert.deepEqual(names, [
      "data_retention",
      "anniversary_scanner",
      "summary_motifs",
      "metadata_enrichment",
      "gap_analysis",
    ]);
  });

  it("hides disabled tasks and healthy non-catch-up tasks", () => {
    const items = [
      task("plot_neighbors", { enabled: false }),
      task("llm_theme_tagging", { enabled: false, last_status: "error: unused" }),
      task("taste_refresh"),
      task("enthusiast_nudge", { last_status: "skipped" }),
    ];
    assert.deepEqual(taskCatchupShortlist(items), []);
  });

  it("keeps a fixable skip with a reason", () => {
    const items = [task("entity_memory_enrichment", { last_status: "skipped", last_outcome_reason: "TMDB key missing" })];
    assert.equal(taskCatchupShortlist(items).length, 1);
  });

  it("keeps a running task even if disabled mid-run", () => {
    const items = [task("plot_neighbors", { enabled: false, running: true })];
    assert.equal(taskCatchupShortlist(items)[0].name, "plot_neighbors");
  });

  it("caps a healthy install at ten rows", () => {
    const items = Array.from({ length: 30 }, (_, i) => task(`t${i}`, { overdue: true }));
    assert.equal(taskCatchupShortlist(items).length, CATCHUP_SHORTLIST_LIMIT);
    assert.equal(CATCHUP_SHORTLIST_LIMIT, 10);
  });

  it("tolerates junk input", () => {
    assert.deepEqual(taskCatchupShortlist(null), []);
    assert.deepEqual(taskCatchupShortlist([null, undefined]), []);
  });
});

describe("resolveTaskView", () => {
  it("defaults to catch-up", () => {
    assert.equal(resolveTaskView(null), "catchup");
    assert.equal(resolveTaskView("bogus"), "catchup");
    assert.equal(resolveTaskView("ALL"), "all");
  });
});

describe("summarizeNeedsAttention", () => {
  it("sorts high first and reports error tone", () => {
    const summary = summarizeNeedsAttention([
      { id: "a", title: "Monday", severity: "low" },
      { id: "b", title: "Keys", severity: "high" },
      { id: "c", title: "Tasks", severity: "medium" },
    ]);
    assert.deepEqual(summary.items.map((i) => i.id), ["b", "c", "a"]);
    assert.equal(summary.tone, "error");
    assert.equal(summary.headline, "3 things need attention");
  });

  it("is calm when empty and drops malformed rows", () => {
    const summary = summarizeNeedsAttention([{ id: "", title: "x" }, null]);
    assert.equal(summary.count, 0);
    assert.equal(summary.tone, "good");
    assert.equal(summary.headline, "Nothing needs attention");
  });

  it("uses singular copy for one row", () => {
    const summary = summarizeNeedsAttention([{ id: "a", title: "x", severity: "medium" }]);
    assert.equal(summary.headline, "1 thing needs attention");
    assert.equal(summary.tone, "warn");
  });
});

describe("secrets card copy", () => {
  it("maps states to tones", () => {
    assert.equal(secretStateCopy("needs_key").tone, "error");
    assert.equal(secretStateCopy("connected").label, "Connected");
    assert.equal(secretStateCopy("weird").label, "Not set up");
  });

  it("formats the last Test time", () => {
    assert.equal(formatLastProbe(null), "Never tested");
    assert.match(formatLastProbe("2026-10-30 12:00:00"), /^Tested /);
    assert.equal(formatLastProbe("not a date"), "Tested not a date");
  });
});

describe("checklistProgress", () => {
  it("counts done, skipped, and open", () => {
    assert.deepEqual(
      checklistProgress([{ status: "done" }, { status: "skipped" }, { status: "pending" }]),
      { done: 1, skipped: 1, total: 3, open: 1 },
    );
  });
});

describe("audit labels", () => {
  it("labels events and falls back to words", () => {
    assert.equal(auditEventLabel("password_reset"), "Password reset by owner");
    assert.equal(auditEventLabel("new_thing"), "new thing");
  });

  it("summarizes detail without values", () => {
    assert.equal(auditDetailLine({ detail: { before: "member", after: "owner" } }), "member → owner");
    assert.equal(
      auditDetailLine({ detail: { fields: ["a", "b", "c", "d", "e"] } }),
      "a, b, c, d +1 more",
    );
    assert.equal(auditDetailLine({ detail: { method: "local", username: "sam" } }), "via local · as “sam”");
    assert.equal(auditDetailLine({}), "");
  });
});

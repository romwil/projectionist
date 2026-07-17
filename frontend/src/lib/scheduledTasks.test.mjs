import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  WARM_EXPLORE_TASKS,
  estimateThroughputEta,
  formatDurationMs,
  formatEtaDuration,
  formatInterval,
  formatLastOutcomeLine,
  formatLogLine,
  formatOutcomeReason,
  formatRunSummaryLine,
  formatTaskLastRun,
  formatTaskLastRunDetail,
  formatThroughputEstimate,
  isTaskRunning,
  resolveLastOutcome,
  resolveRunMetrics,
  resolveWarmExploreTasks,
  summarizeLastStatus,
  taskDisplayName,
  taskRowTone,
} from "./scheduledTasks.js";

describe("scheduledTasks helpers", () => {
  it("formats known and unknown task names", () => {
    assert.equal(taskDisplayName("health_metrics"), "Health metrics");
    assert.equal(taskDisplayName("custom_thing"), "Custom Thing");
  });

  it("formats intervals and durations", () => {
    assert.equal(formatInterval(45), "45s");
    assert.equal(formatInterval(3600), "1h");
    assert.equal(formatInterval(86400), "1d");
    assert.equal(formatDurationMs(850), "850ms");
    assert.equal(formatDurationMs(1500), "1.5s");
    assert.equal(formatDurationMs(125000), "2m 5s");
  });

  it("summarizes status and running state", () => {
    assert.equal(summarizeLastStatus("completed"), "Succeeded");
    assert.equal(summarizeLastStatus("skipped"), "Skipped");
    assert.equal(summarizeLastStatus("error: boom"), "Failed");
    assert.equal(summarizeLastStatus(null), "Never run");
    assert.equal(isTaskRunning({ running: true }), true);
    assert.equal(isTaskRunning({ current_run: { run_id: "abc" } }), true);
    assert.equal(isTaskRunning({ running: false }), false);
  });

  it("formats skip/fail outcome reasons", () => {
    assert.equal(
      formatOutcomeReason({ outcome_reason: "OpenAI/LLM API key not configured" }),
      "OpenAI/LLM API key not configured",
    );
    assert.match(
      formatLastOutcomeLine({
        last_status: "skipped",
        last_finished_at: 1_700_000_000,
        last_outcome_reason: "Theme tagging is not implemented yet (stub task)",
      }),
      /Skipped · .* — Theme tagging is not implemented yet/,
    );
    assert.equal(
      resolveLastOutcome({ last_status: "skipped", summary: { note: "Nothing to tag" } }).reason,
      "Nothing to tag",
    );
  });

  it("formats run summary lines and last-run detail", () => {
    assert.equal(
      formatRunSummaryLine({
        last_run_summary_line: "5 enriched · 0 errors",
      }),
      "5 enriched · 0 errors",
    );
    assert.equal(
      formatTaskLastRunDetail({
        last_status: "completed",
        last_run_summary: { summary_line: "3 caches warmed · 120 library items" },
      }),
      "3 caches warmed · 120 library items",
    );
    assert.deepEqual(
      resolveRunMetrics({ last_run_summary: { metrics: { enriched: 2 } } }),
      { enriched: 2 },
    );
  });

  it("picks row tone from task state", () => {
    assert.equal(taskRowTone({ running: true }), "running");
    assert.equal(taskRowTone({ quarantine: { is_quarantined: true } }), "quarantined");
    assert.equal(taskRowTone({ last_status: "error: x" }), "error");
    assert.equal(taskRowTone({ last_status: "skipped" }), "skipped");
    assert.equal(taskRowTone({ enabled: false }), "disabled");
    assert.equal(taskRowTone({ enabled: true, overdue: true }), "overdue");
  });

  it("formats log lines", () => {
    const line = formatLogLine({
      ts: 1_700_000_000,
      level: "info",
      message: "Started (manual)",
    });
    assert.match(line, /INFO/);
    assert.match(line, /Started \(manual\)/);

    const skipped = formatLogLine({
      ts: 1_700_000_001,
      level: "status",
      message: "Skipped — OpenAI/LLM API key not configured",
      data: { outcome_reason: "OpenAI/LLM API key not configured" },
    });
    assert.match(skipped, /Skipped — OpenAI\/LLM API key not configured/);
  });

  it("resolves Warm Explore preset against available tasks", () => {
    assert.ok(WARM_EXPLORE_TASKS.includes("plot_neighbors"));
    assert.deepEqual(
      resolveWarmExploreTasks([
        { name: "plot_neighbors" },
        { name: "health_metrics" },
        { name: "metadata_enrichment" },
      ]),
      ["metadata_enrichment", "plot_neighbors"],
    );
    assert.match(formatTaskLastRun({ last_status: "completed", last_finished_at: null }), /Succeeded/);
  });

  it("estimates throughput ETA when cadence changes", () => {
    const progress = {
      remaining_items: 100,
      items_per_cycle: 25,
      scope_label: "titles still missing TMDB dates/plot",
    };
    const atSixHours = estimateThroughputEta(progress, 21600);
    assert.equal(atSixHours.estimated_cycles, 4);
    assert.equal(atSixHours.estimated_seconds, 86400);
    const atOneDay = estimateThroughputEta(progress, 86400);
    assert.equal(atOneDay.estimated_seconds, 345600);
    assert.match(formatThroughputEstimate(atSixHours), /≈ ~1d/);
    assert.equal(
      formatThroughputEstimate({ ...progress, remaining_items: 0, estimated_seconds: 0 }),
      "Caught up — no titles still missing TMDB dates/plot right now.",
    );
    assert.equal(formatEtaDuration(0), "caught up");
    assert.equal(formatEtaDuration(90 * 86400), "~3mo");
  });
});

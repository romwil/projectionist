import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  WARM_EXPLORE_TASKS,
  formatDurationMs,
  formatInterval,
  formatLogLine,
  formatTaskLastRun,
  isTaskRunning,
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
    assert.equal(summarizeLastStatus("error: boom"), "Failed");
    assert.equal(summarizeLastStatus(null), "Never run");
    assert.equal(isTaskRunning({ running: true }), true);
    assert.equal(isTaskRunning({ current_run: { run_id: "abc" } }), true);
    assert.equal(isTaskRunning({ running: false }), false);
  });

  it("picks row tone from task state", () => {
    assert.equal(taskRowTone({ running: true }), "running");
    assert.equal(taskRowTone({ quarantine: { is_quarantined: true } }), "quarantined");
    assert.equal(taskRowTone({ last_status: "error: x" }), "error");
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
});

import assert from "node:assert/strict";
import test from "node:test";
import {
  guardrailStatusCopy,
  guardrailValueText,
  sparklineLabel,
  sparklinePoints,
  weekOverWeek,
} from "./householdPulse.ts";

test("week over week reads as plain words", () => {
  assert.deepEqual(weekOverWeek(5, 3), { direction: "up", text: "Up 2 from last week" });
  assert.deepEqual(weekOverWeek(1, 4), { direction: "down", text: "Down 3 from last week" });
  assert.equal(weekOverWeek(0, 0).direction, "flat");
});

test("sparkline scales to the tallest week and announces its values", () => {
  assert.equal(sparklinePoints([0, 2, 4], 10, 4), "0,4 5,2 10,0");
  assert.equal(sparklinePoints([]), "");
  assert.equal(sparklineLabel([1, 0, 3]), "Last 3 weeks, oldest first: 1, 0, 3");
});

test("guardrail values carry units and limits", () => {
  assert.equal(
    guardrailValueText({ id: "chat_failure_rate", label: "", value: 0.091, limit: 0.05, status: "watch" }),
    "9.1% (limit 5%)",
  );
  assert.equal(
    guardrailValueText({ id: "chat_p95_ms", label: "", value: 4200, limit: 12000, status: "ok" }),
    "4.2 s (limit 12 s)",
  );
  assert.equal(guardrailValueText({ id: "llm_spend", label: "", value: 1.5, limit: null, status: "ok" }), "$1.50");
  assert.equal(guardrailValueText({ id: "x", label: "", value: null, limit: null, status: "no_data" }), "No data yet");
  assert.equal(guardrailStatusCopy("watch"), "Watch");
});

import assert from "node:assert/strict";
import test from "node:test";

import { agentPulseTitle, curatorxBrandAriaLabel, resolveAgentPulse } from "./agentPulse.js";

test("resolveAgentPulse ignores jobs and stays idle by default", () => {
  assert.equal(resolveAgentPulse(), "idle");
  assert.equal(resolveAgentPulse({}), "idle");
  // Historical failed syncs must not drive the pulse
  assert.equal(resolveAgentPulse({ loading: false, chatError: "" }), "idle");
});

test("resolveAgentPulse shows thinking while chat is loading", () => {
  assert.equal(resolveAgentPulse({ loading: true }), "thinking");
  assert.equal(resolveAgentPulse({ loading: true, chatError: "" }), "thinking");
});

test("resolveAgentPulse shows error only for chat agent failures", () => {
  assert.equal(resolveAgentPulse({ chatError: "Request timed out" }), "error");
  assert.equal(resolveAgentPulse({ loading: false, chatError: "LLM failed" }), "error");
});

test("loading clears visual priority once chatError is cleared by a new send", () => {
  assert.equal(resolveAgentPulse({ loading: true, chatError: "" }), "thinking");
  assert.equal(resolveAgentPulse({ loading: false, chatError: "" }), "idle");
});

test("agentPulseTitle is accurate for each state", () => {
  assert.equal(agentPulseTitle("idle"), "Agent idle");
  assert.equal(agentPulseTitle("thinking"), "Agent thinking");
  assert.equal(agentPulseTitle("error"), "Agent error");
  assert.equal(agentPulseTitle("error", "Request timed out"), "Agent error: Request timed out");
});

test("agentPulseTitle truncates long chat errors", () => {
  const long = "x".repeat(150);
  const title = agentPulseTitle("error", long);
  assert.match(title, /^Agent error: /);
  assert.ok(title.length <= "Agent error: ".length + 120);
  assert.ok(title.endsWith("..."));
});

test("agentPulseTitle treats running like thinking", () => {
  assert.equal(agentPulseTitle("running"), "Agent thinking");
});

test("curatorxBrandAriaLabel prefixes home label with activity status", () => {
  assert.equal(curatorxBrandAriaLabel("idle"), "CuratorX home — Agent idle");
  assert.equal(curatorxBrandAriaLabel("thinking"), "CuratorX home — Agent thinking");
  assert.equal(
    curatorxBrandAriaLabel("error", "Request timed out"),
    "CuratorX home — Agent error: Request timed out",
  );
});

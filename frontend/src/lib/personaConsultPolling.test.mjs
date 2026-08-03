import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  hasPendingPersonaConsult,
  mergeThreadMessagesById,
  PERSONA_CONSULT_FIRST_POLL_MS,
  PERSONA_CONSULT_POLL_MS,
  PERSONA_CONSULT_POLL_WINDOW_MS,
  shouldSchedulePersonaConsultPoll,
} from "./personaConsultPolling.js";

describe("persona consult polling", () => {
  it("merges callback messages by id without duplicating existing messages", () => {
    const current = [
      { id: "user-1", role: "user", blocks: [{ type: "text", content: "Ask Scholar" }] },
      {
        id: "assistant-1",
        role: "assistant",
        blocks: [{
          type: "persona_consult",
          payload: { consult_id: "consult-1", pending: true, persona: "Scholar" },
        }],
      },
    ];
    const fetched = [
      current[0],
      { ...current[1], created_at: 10 },
      {
        id: "callback-1",
        role: "assistant",
        blocks: [{
          type: "persona_consult",
          payload: { consult_id: "consult-1", answer: "A cited answer." },
        }],
      },
    ];

    const merged = mergeThreadMessagesById(current, fetched);

    assert.deepEqual(merged.map((message) => message.id), [
      "user-1",
      "assistant-1",
      "callback-1",
    ]);
    assert.equal(merged[1].created_at, 10);
  });

  it("drops current messages without ids so they cannot stale in the merge map", () => {
    const current = [
      { id: undefined, role: "assistant", blocks: [{ type: "text", content: "stale" }] },
      { role: "user", blocks: [{ type: "text", content: "also id-less" }] },
      {
        id: "assistant-1",
        role: "assistant",
        blocks: [{
          type: "persona_consult",
          payload: { consult_id: "consult-1", pending: true, persona: "Scholar" },
        }],
      },
    ];
    const fetched = [
      {
        id: "assistant-1",
        role: "assistant",
        blocks: [{
          type: "persona_consult",
          payload: { consult_id: "consult-1", pending: true, persona: "Scholar" },
        }],
        created_at: 10,
      },
      {
        id: "callback-1",
        role: "assistant",
        blocks: [{
          type: "persona_consult",
          payload: { consult_id: "consult-1", answer: "A cited answer." },
        }],
      },
      { role: "assistant", blocks: [{ type: "text", content: "fetched without id" }] },
    ];

    const merged = mergeThreadMessagesById(current, fetched);

    assert.deepEqual(merged.map((message) => message.id), ["assistant-1", "callback-1"]);
    assert.equal(merged[0].created_at, 10);
    assert.equal(
      merged.some((message) => message.blocks?.[0]?.content === "stale"),
      false,
    );
  });

  it("polls only while a pending consult has no matching callback", () => {
    const pending = {
      id: "assistant-1",
      blocks: [{
        type: "persona_consult",
        payload: { consult_id: "consult-1", pending: true },
      }],
    };
    const callback = {
      id: "callback-1",
      blocks: [{
        type: "persona_consult",
        payload: { consult_id: "consult-1", answer: "Called back." },
      }],
    };

    assert.equal(hasPendingPersonaConsult([pending]), true);
    assert.equal(hasPendingPersonaConsult([pending, callback]), false);
  });

  it("allows one final poll when the prior request crosses the deadline", () => {
    const deadline = 60_000;

    assert.equal(
      shouldSchedulePersonaConsultPoll({
        pollStartedAt: deadline - 100,
        deadline,
      }),
      true,
    );
    assert.equal(
      shouldSchedulePersonaConsultPoll({
        pollStartedAt: deadline + PERSONA_CONSULT_POLL_MS,
        deadline,
      }),
      false,
    );
  });

  it("covers the backend hard deadline plus polling grace", () => {
    const backendHardDeadlineMs = 55_000;

    assert.ok(
      PERSONA_CONSULT_POLL_WINDOW_MS >=
        backendHardDeadlineMs +
          PERSONA_CONSULT_FIRST_POLL_MS +
          PERSONA_CONSULT_POLL_MS,
    );
  });
});

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

  it("does not replay later user turns when the poll snapshot uses server ids", () => {
    const pending = {
      id: "assistant-1",
      role: "assistant",
      blocks: [{
        type: "persona_consult",
        payload: { consult_id: "consult-1", pending: true, persona: "The Professor" },
      }],
    };
    const laterUser = {
      id: "optimistic-user-2",
      role: "user",
      blocks: [{ type: "text", content: "it's been a while! what's new?" }],
    };
    const laterAssistant = {
      id: "assistant-2",
      role: "assistant",
      blocks: [{ type: "text", content: "Dolly Parton movies landed on the shelf." }],
    };
    const current = [
      { id: "user-1", role: "user", blocks: [{ type: "text", content: "Ask The Professor" }] },
      pending,
      laterUser,
      laterAssistant,
    ];
    const addendum = {
      id: "persona-consult-consult-1",
      role: "assistant",
      blocks: [
        { type: "text", content: "**Addendum — The Professor called back.**" },
        {
          type: "persona_consult",
          payload: { consult_id: "consult-1", answer: "A cited answer." },
        },
      ],
    };
    const fetched = [
      current[0],
      pending,
      { ...laterUser, id: "server-user-2", created_at: 20 },
      { ...laterAssistant, created_at: 21 },
      addendum,
    ];

    const merged = mergeThreadMessagesById(current, fetched);

    assert.deepEqual(
      merged.map((message) => message.id),
      ["user-1", "assistant-1", "server-user-2", "assistant-2", "persona-consult-consult-1"],
    );
    assert.equal(
      merged.filter((message) => message.role === "user").length,
      2,
    );
    assert.equal(merged[2].blocks[0].content, laterUser.blocks[0].content);
    assert.equal(merged[4].blocks[0].content, addendum.blocks[0].content);
  });

  it("keeps an in-flight optimistic user turn that the snapshot has not persisted yet", () => {
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
      { id: "optimistic-user-2", role: "user", blocks: [{ type: "text", content: "still typing a follow-up" }] },
    ];
    const fetched = [current[0], current[1]];

    const merged = mergeThreadMessagesById(current, fetched);

    assert.deepEqual(
      merged.map((message) => message.id),
      ["user-1", "assistant-1", "optimistic-user-2"],
    );
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

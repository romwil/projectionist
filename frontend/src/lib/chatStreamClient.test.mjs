import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const clientSrc = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "../api/client.js"),
  "utf8",
);

describe("sendChatStream", () => {
  it("POSTs JSON and reads the body; never constructs EventSource", () => {
    const start = clientSrc.indexOf("export async function sendChatStream");
    const nextExport = clientSrc.indexOf("\nexport ", start + 1);
    const fn = clientSrc.slice(start, nextExport === -1 ? undefined : nextExport);
    assert.match(fn, /method:\s*["']POST["']/);
    assert.match(fn, /JSON\.stringify\(body\)/);
    assert.match(fn, /response\.body\.getReader\(\)/);
    assert.equal(fn.includes("EventSource"), false);
    assert.equal(fn.includes("URLSearchParams"), false);
    assert.equal(fn.includes("new EventSource"), false);
  });
});

function sseResponse(chunks) {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
        controller.close();
      },
    }),
    { status: 200 },
  );
}

async function runStream(chunks, extra = {}) {
  const { sendChatStream } = await import("../api/client.js");
  const original = globalThis.fetch;
  globalThis.fetch = async () => sseResponse(chunks);
  const seen = { done: [], errors: [], tokens: [] };
  try {
    await sendChatStream("make a collection", {
      sessionId: "s1",
      onToken: (t) => seen.tokens.push(t),
      onDone: (d) => seen.done.push(d),
      onError: (e) => seen.errors.push(e),
      ...extra,
    });
  } finally {
    globalThis.fetch = original;
  }
  return seen;
}

describe("sendChatStream terminal events", () => {
  it("reports an error when the stream closes after tool work with no done/error", async () => {
    const seen = await runStream([
      'event: tool_call\ndata: {"name":"confirm_pending_action","status":"start"}\n\n',
    ]);
    assert.equal(seen.done.length, 0);
    assert.equal(seen.errors.length, 1);
    assert.match(seen.errors[0].error, /stopped before it finished/i);
  });

  it("does not add a synthetic error after a normal done event", async () => {
    const seen = await runStream([
      'event: token\ndata: {"content":"hi"}\n\n',
      'event: done\ndata: {"message":{"blocks":[]}}\n\n',
    ]);
    assert.equal(seen.done.length, 1);
    assert.equal(seen.errors.length, 0);
  });

  it("does not double-report when the server already sent an error event", async () => {
    const seen = await runStream(['event: error\ndata: {"error":"Plex said no"}\n\n']);
    assert.deepEqual(seen.errors, [{ error: "Plex said no" }]);
  });
});

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

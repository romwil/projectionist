import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createId } from "./id.js";

describe("createId", () => {
  it("returns a hyphenated UUID-shaped string by default", () => {
    const id = createId();
    assert.match(id, /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i);
  });

  it("returns a compact 32-char hex string when requested", () => {
    const id = createId({ compact: true });
    assert.match(id, /^[0-9a-f]{32}$/i);
  });

  it("works when crypto.randomUUID is unavailable (non-secure HTTP)", () => {
    const original = crypto.randomUUID;
    try {
      Object.defineProperty(crypto, "randomUUID", {
        configurable: true,
        value: undefined,
      });
      assert.equal(typeof crypto.randomUUID, "undefined");
      const id = createId({ compact: true });
      assert.match(id, /^[0-9a-f]{32}$/i);
    } finally {
      Object.defineProperty(crypto, "randomUUID", {
        configurable: true,
        value: original,
      });
    }
  });

  it("falls back when crypto.randomUUID throws (non-secure context)", () => {
    const original = crypto.randomUUID;
    try {
      Object.defineProperty(crypto, "randomUUID", {
        configurable: true,
        value: () => {
          throw new Error("Secure context required");
        },
      });
      const id = createId();
      assert.match(id, /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i);
      const compact = createId({ compact: true });
      assert.match(compact, /^[0-9a-f]{32}$/i);
    } finally {
      Object.defineProperty(crypto, "randomUUID", {
        configurable: true,
        value: original,
      });
    }
  });

  it("produces distinct ids", () => {
    const ids = new Set(Array.from({ length: 20 }, () => createId({ compact: true })));
    assert.equal(ids.size, 20);
  });

  it("falls back to Math.random when getRandomValues is also missing", () => {
    const originalUUID = crypto.randomUUID;
    const originalGRV = crypto.getRandomValues;
    try {
      Object.defineProperty(crypto, "randomUUID", {
        configurable: true,
        value: undefined,
      });
      Object.defineProperty(crypto, "getRandomValues", {
        configurable: true,
        value: undefined,
      });
      const id = createId();
      assert.match(id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
      const compact = createId({ compact: true });
      assert.match(compact, /^[0-9a-f]{32}$/i);
    } finally {
      Object.defineProperty(crypto, "randomUUID", {
        configurable: true,
        value: originalUUID,
      });
      Object.defineProperty(crypto, "getRandomValues", {
        configurable: true,
        value: originalGRV,
      });
    }
  });

  it("keeps hyphenated form when only randomUUID is missing", () => {
    const original = crypto.randomUUID;
    try {
      Object.defineProperty(crypto, "randomUUID", {
        configurable: true,
        value: undefined,
      });
      const id = createId();
      assert.match(id, /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i);
      assert.equal(id.includes("-"), true);
    } finally {
      Object.defineProperty(crypto, "randomUUID", {
        configurable: true,
        value: original,
      });
    }
  });
});

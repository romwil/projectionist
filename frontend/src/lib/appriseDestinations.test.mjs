import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  appriseSchemeOf,
  appriseTypeLabel,
  buildAppriseUrl,
  detectBuilderScheme,
  maskAppriseUrl,
  parseAppriseDestinationRows,
  parseAppriseUrlFields,
  serializeAppriseDestinationRows,
  splitAppriseUrls,
} from "./appriseDestinations.js";

describe("splitAppriseUrls", () => {
  it("splits newlines and skips comments", () => {
    assert.deepEqual(
      splitAppriseUrls("discord://a/b\n# comment\ntgram://bot/chat"),
      ["discord://a/b", "tgram://bot/chat"],
    );
  });

  it("dedupes and tolerates commas", () => {
    assert.deepEqual(splitAppriseUrls("json://x, json://x; ntfy://topic"), [
      "json://x",
      "ntfy://topic",
    ]);
  });
});

describe("parse/serialize rows", () => {
  it("round-trips a URL list", () => {
    const rows = parseAppriseDestinationRows("discord://id/token\npover://user@tok");
    assert.equal(rows.length, 2);
    assert.equal(rows[0].url, "discord://id/token");
    assert.equal(
      serializeAppriseDestinationRows(rows),
      "discord://id/token\npover://user@tok",
    );
  });
});

describe("labels and schemes", () => {
  it("detects common schemes", () => {
    assert.equal(appriseSchemeOf("tgram://bot/chat"), "tgram");
    assert.equal(appriseTypeLabel("tgram://bot/chat"), "Telegram");
    assert.equal(detectBuilderScheme("mailtos://u:p@h:587?to=a@b.c"), "mailto");
    assert.equal(detectBuilderScheme("json://localhost/x"), "custom");
  });
});

describe("maskAppriseUrl", () => {
  it("keeps scheme and masks path secrets", () => {
    const masked = maskAppriseUrl("discord://123456789012345678/supersecrettokenvalue");
    assert.match(masked, /^discord:\/\//);
    assert.doesNotMatch(masked, /supersecrettokenvalue/);
    assert.ok(masked.includes("…"));
  });
});

describe("buildAppriseUrl", () => {
  it("builds Discord, Telegram, Slack, Pushover", () => {
    assert.equal(
      buildAppriseUrl("discord", { webhook_id: "111", webhook_token: "tok" }),
      "discord://111/tok/",
    );
    assert.equal(
      buildAppriseUrl("telegram", { bot_token: "1:ABC", chat_id: "-100" }),
      "tgram://1:ABC/-100",
    );
    assert.equal(
      buildAppriseUrl("slack", { token_a: "T1", token_b: "B2", token_c: "X3" }),
      "slack://T1/B2/X3/",
    );
    assert.equal(
      buildAppriseUrl("pushover", { user_key: "user", api_token: "app" }),
      "pover://user@app",
    );
  });

  it("builds mailto, gotify, ntfy, and custom", () => {
    assert.equal(
      buildAppriseUrl("mailto", {
        user: "u",
        password: "p",
        host: "smtp.example.com",
        port: "587",
        to: "you@example.com",
        use_tls: "1",
      }),
      "mailtos://u:p@smtp.example.com:587?to=you%40example.com",
    );
    assert.equal(
      buildAppriseUrl("gotify", { host: "g.example", token: "tok", use_tls: "1" }),
      "gotifys://g.example/tok",
    );
    assert.equal(buildAppriseUrl("ntfy", { topic: "alerts" }), "ntfy://alerts");
    assert.equal(
      buildAppriseUrl("custom", { url: "json://localhost/hook" }),
      "json://localhost/hook",
    );
  });

  it("rejects incomplete forms", () => {
    assert.throws(() => buildAppriseUrl("discord", { webhook_id: "1" }), /webhook/i);
    assert.throws(() => buildAppriseUrl("custom", { url: "not-a-url" }), /scheme/i);
  });
});

describe("parseAppriseUrlFields", () => {
  it("parses Discord and ntfy back into fields", () => {
    const discord = parseAppriseUrlFields("discord://111/tok/");
    assert.equal(discord.schemeId, "discord");
    assert.equal(discord.fields.webhook_id, "111");
    assert.equal(discord.fields.webhook_token, "tok");

    const ntfy = parseAppriseUrlFields("ntfys://ntfy.example/alerts");
    assert.equal(ntfy.schemeId, "ntfy");
    assert.equal(ntfy.fields.host, "ntfy.example");
    assert.equal(ntfy.fields.topic, "alerts");
    assert.equal(ntfy.fields.use_tls, "1");
  });

  it("falls back to custom for unknown schemes", () => {
    const custom = parseAppriseUrlFields("json://localhost/x");
    assert.equal(custom.schemeId, "custom");
    assert.equal(custom.fields.url, "json://localhost/x");
  });
});

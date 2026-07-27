import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { formatApiError, looksLikeHtmlOrMarkup, parseApiErrorBody } from "./apiError.js";

describe("parseApiErrorBody", () => {
  it("prefers FastAPI JSON detail strings", () => {
    assert.equal(
      parseApiErrorBody(JSON.stringify({ detail: "Invalid credentials" }), "Bad Request", 400),
      "Invalid credentials",
    );
  });

  it("joins validation detail arrays", () => {
    const body = JSON.stringify({
      detail: [{ msg: "field required" }, { msg: "too short" }],
    });
    assert.equal(parseApiErrorBody(body, "Unprocessable", 422), "field required; too short");
  });

  it("does not dump Cloudflare HTML 502 pages", () => {
    const html = `<!DOCTYPE html>
<html>
<head><title>502 Bad gateway</title></head>
<body>
<div class="cf-error-details error-code">
  <h1>Bad gateway</h1>
  <span>Cloudflare</span>
</div>
</body>
</html>`;
    assert.equal(
      parseApiErrorBody(html, "Bad Gateway", 502),
      "The server is temporarily unavailable. Try again in a moment.",
    );
    assert.equal(looksLikeHtmlOrMarkup(html), true);
  });

  it("maps other gateway statuses without exposing markup", () => {
    assert.equal(
      parseApiErrorBody("<html><body>down</body></html>", "Service Unavailable", 503),
      "The server is temporarily unavailable. Try again in a moment.",
    );
    assert.equal(
      parseApiErrorBody("<html>timeout</html>", "Gateway Timeout", 504),
      "The server took too long to respond. Try again in a moment.",
    );
  });

  it("keeps short plain-text bodies", () => {
    assert.equal(parseApiErrorBody("Plex PIN expired", "Bad Request", 400), "Plex PIN expired");
  });

  it("falls back when the body is empty", () => {
    assert.equal(
      parseApiErrorBody("", "Too Many Requests", 429),
      "Too many attempts. Wait a moment and try again.",
    );
  });
});

describe("formatApiError", () => {
  it("special-cases abort timeouts", () => {
    const err = new Error("aborted");
    err.name = "AbortError";
    assert.match(formatApiError(err), /timed out/i);
  });

  it("returns the error message when present", () => {
    assert.equal(formatApiError(new Error("Nope")), "Nope");
  });
});

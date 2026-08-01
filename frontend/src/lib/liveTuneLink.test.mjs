import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { liveTuneAbsoluteUrl, tuneLinkCardDataUrl } from "./liveTuneLink.js";

describe("liveTuneLink", () => {
  it("builds an absolute watch deep-link", () => {
    const url = liveTuneAbsoluteUrl("abc-123", { origin: "http://tv.local:8788" });
    assert.equal(url, "http://tv.local:8788/live?channel=abc-123");
  });

  it("builds a CSP-safe SVG link card data URL", () => {
    const card = tuneLinkCardDataUrl("http://tv.local:8788/live?channel=abc");
    assert.match(card, /^data:image\/svg\+xml/);
    assert.match(card, /Tune%20link|Tune link/);
  });
});

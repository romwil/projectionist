import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  ROUTES,
  backLabelForPath,
  resolveBackTarget,
  withReturnTo,
} from "./backNav.js";

describe("resolveBackTarget", () => {
  it("prefers internal from state over fallback", () => {
    assert.equal(resolveBackTarget({ from: "/explore/tags" }, ROUTES.chat), "/explore/tags");
  });

  it("rejects external or protocol-relative from", () => {
    assert.equal(resolveBackTarget({ from: "https://evil.test" }, ROUTES.explore), ROUTES.explore);
    assert.equal(resolveBackTarget({ from: "//evil.test" }, ROUTES.explore), ROUTES.explore);
  });

  it("falls back when from missing", () => {
    assert.equal(resolveBackTarget(null, ROUTES.tags), ROUTES.tags);
  });
});

describe("backLabelForPath", () => {
  it("labels explore contexts specifically", () => {
    assert.equal(backLabelForPath("/explore/tags"), "Back to tag search");
    assert.equal(backLabelForPath("/explore/plot-lab"), "Back to Plot Lab");
    assert.equal(backLabelForPath("/explore/section/recently-added"), "Back to Explore");
    assert.equal(backLabelForPath("/explore"), "Back to Explore");
    assert.equal(backLabelForPath("/"), "Back to chat");
  });
});

describe("withReturnTo", () => {
  it("stores pathname and search", () => {
    assert.deepEqual(withReturnTo("/explore", "?genre=Horror"), {
      from: "/explore?genre=Horror",
    });
  });
});

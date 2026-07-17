import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  ROUTES,
  backLabelForPath,
  isWatchlistPanelRequest,
  resolveBackTarget,
  stripWatchlistPanelParam,
  watchlistBrowseHref,
  watchlistPanelHref,
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

describe("watchlist browse route", () => {
  it("exposes a dedicated /watchlist route", () => {
    assert.equal(ROUTES.watchlist, "/watchlist");
    assert.equal(watchlistBrowseHref(), "/watchlist");
  });

  it("labels the watchlist page back link", () => {
    assert.equal(backLabelForPath("/watchlist"), "Back to chat");
  });
});

describe("watchlist panel deep link (legacy)", () => {
  it("builds chat href that opens the panel", () => {
    assert.equal(watchlistPanelHref(), "/?watchlist=1");
  });

  it("detects open request values", () => {
    assert.equal(isWatchlistPanelRequest(new URLSearchParams("watchlist=1")), true);
    assert.equal(isWatchlistPanelRequest(new URLSearchParams("watchlist=open")), true);
    assert.equal(isWatchlistPanelRequest(new URLSearchParams("watchlist=true")), true);
    assert.equal(isWatchlistPanelRequest(new URLSearchParams("watchlist=0")), false);
    assert.equal(isWatchlistPanelRequest(new URLSearchParams("")), false);
  });

  it("strips the panel flag without dropping other params", () => {
    const next = stripWatchlistPanelParam(new URLSearchParams("watchlist=1&foo=bar"));
    assert.equal(next.get("watchlist"), null);
    assert.equal(next.get("foo"), "bar");
  });
});

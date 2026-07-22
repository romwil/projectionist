import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  RECOMMEND_LIKE_PARAM,
  ROUTES,
  backLabelForPath,
  chatFromRailHref,
  chatFromRailPrompt,
  recommendLikeHref,
  recommendLikePrompt,
  isWatchlistPanelRequest,
  resolveBackTarget,
  stripChatFromRailParam,
  stripRecommendLikeParam,
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
    assert.equal(backLabelForPath("/explore/browse"), "Back to Explore");
    assert.equal(backLabelForPath("/explore/browse?media_type=movie"), "Back to Explore");
    assert.equal(backLabelForPath("/explore"), "Back to Explore");
    assert.equal(backLabelForPath("/"), "Back to chat");
    assert.equal(backLabelForPath("/privacy"), "Back to Privacy");
  });
});

describe("ROUTES.privacy", () => {
  it("exposes the privacy disclosure path", () => {
    assert.equal(ROUTES.privacy, "/privacy");
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

describe("recommend like chat deep link", () => {
  it("preserves a concise media context in the chat URL", () => {
    assert.equal(
      recommendLikeHref({ title: "Arrival", year: 2016, media_type: "movie" }),
      "/?recommend_like=Arrival&year=2016&type=movie",
    );
  });

  it("builds an agent-ready prompt and removes only its parameters", () => {
    const params = new URLSearchParams("recommend_like=Arrival&year=2016&type=movie&foo=bar");
    assert.equal(RECOMMEND_LIKE_PARAM, "recommend_like");
    assert.equal(
      recommendLikePrompt(params),
      'Recommend titles like "Arrival" (2016, movie) and help me discuss what makes it work.',
    );
    const next = stripRecommendLikeParam(params);
    assert.equal(next.get("recommend_like"), null);
    assert.equal(next.get("year"), null);
    assert.equal(next.get("type"), null);
    assert.equal(next.get("foo"), "bar");
  });
});

describe("chat from rail deep link", () => {
  it("seeds a rail-level conversation", () => {
    const href = chatFromRailHref({
      railTitle: "For you this week",
      items: [{ title: "Heat" }, { title: "Arrival" }],
    });
    assert.match(href, /from_rail=1/);
    assert.match(href, /rail_title=For\+you\+this\+week/);
    const params = new URLSearchParams(href.replace("/?", ""));
    assert.match(
      chatFromRailPrompt(params),
      /For you this week/,
    );
    assert.match(chatFromRailPrompt(params), /Heat/);
  });

  it("seeds a single focused title with why", () => {
    const href = chatFromRailHref(
      { railTitle: "For you this week" },
      { title: "Heat", why: "Fits your noir lean" },
    );
    const params = new URLSearchParams(href.replace("/?", ""));
    const prompt = chatFromRailPrompt(params);
    assert.match(prompt, /Heat/);
    assert.match(prompt, /noir lean/);
    const stripped = stripChatFromRailParam(params);
    assert.equal(stripped.get("from_rail"), null);
    assert.equal(stripped.get("rail_why"), null);
  });
});

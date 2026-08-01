import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  CHAT_ABOUT_TITLE_WHY,
  RECOMMEND_LIKE_PARAM,
  ROUTES,
  backLabelForPath,
  chatAboutTitleHref,
  chatAboutTitleSeed,
  chatFromRailHref,
  chatFromRailPrompt,
  recommendLikeHref,
  recommendLikePrompt,
  isWatchlistPanelRequest,
  resolveBackTarget,
  resolveTitleBackNav,
  returnStateFromLocation,
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

  it("labels chat and search origins", () => {
    assert.equal(backLabelForPath("/chat"), "Back to chat");
    assert.equal(backLabelForPath("/chat?session=abc"), "Back to chat");
    assert.equal(backLabelForPath("/search"), "Back to Search");
    assert.equal(backLabelForPath("/search?q=heat"), "Back to Search");
  });
});

describe("resolveTitleBackNav", () => {
  it("returns chat label/href from chat rail origin", () => {
    assert.deepEqual(resolveTitleBackNav({ from: "/chat" }), {
      to: "/chat",
      label: "Back to chat",
    });
  });

  it("returns explore label/href from explore origin", () => {
    assert.deepEqual(resolveTitleBackNav({ from: "/explore" }), {
      to: "/explore",
      label: "Back to Explore",
    });
  });

  it("returns search label/href and preserves query", () => {
    assert.deepEqual(resolveTitleBackNav({ from: "/search?q=unexpected" }), {
      to: "/search?q=unexpected",
      label: "Back to Search",
    });
  });

  it("defaults to chat when no from state", () => {
    assert.deepEqual(resolveTitleBackNav(null), {
      to: ROUTES.chat,
      label: "Back to chat",
    });
  });
});

describe("returnStateFromLocation", () => {
  it("records the current path as from", () => {
    assert.deepEqual(returnStateFromLocation({ pathname: "/chat", search: "" }), {
      from: "/chat",
    });
    assert.deepEqual(
      returnStateFromLocation({ pathname: "/search", search: "?q=heat" }),
      { from: "/search?q=heat" },
    );
  });

  it("preserves an existing from when hopping title to title", () => {
    assert.deepEqual(
      returnStateFromLocation({
        pathname: "/title/show/2199",
        search: "",
        state: { from: "/chat" },
      }),
      { from: "/chat" },
    );
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

  it("defaults empty origin to chat", () => {
    assert.deepEqual(withReturnTo(""), { from: ROUTES.chat });
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
    assert.equal(watchlistPanelHref(), "/chat?watchlist=1");
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
      "/chat?recommend_like=Arrival&year=2016&type=movie",
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
    assert.match(href, /^\/chat\?/);
    const params = new URLSearchParams(href.split("?")[1] || "");
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
    const params = new URLSearchParams(href.split("?")[1] || "");
    const prompt = chatFromRailPrompt(params);
    assert.match(prompt, /Let's discuss/);
    assert.match(prompt, /Heat/);
    assert.match(prompt, /noir lean/);
    assert.match(prompt, /from my "For you this week" picks/);
    const stripped = stripChatFromRailParam(params);
    assert.equal(stripped.get("from_rail"), null);
    assert.equal(stripped.get("rail_why"), null);
  });

  it("encodes stable ids and why into the prompt pack", () => {
    const href = chatFromRailHref({
      railTitle: "For you this week",
      railId: "rail-abc",
      items: [
        {
          id: 42,
          title: "Heat",
          year: 1995,
          media_type: "movie",
          rating_key: "rk-heat",
          why: "Fits your noir lean",
        },
      ],
    });
    assert.match(href, /rail_id=rail-abc/);
    assert.match(href, /rail_pack=/);
    const params = new URLSearchParams(href.split("?")[1] || "");
    const prompt = chatFromRailPrompt(params);
    assert.match(prompt, /library_id=42/);
    assert.match(prompt, /rating_key=rk-heat/);
    assert.match(prompt, /noir lean/);
    assert.match(prompt, /Do NOT search TMDB/);
    const stripped = stripChatFromRailParam(params);
    assert.equal(stripped.get("rail_pack"), null);
    assert.equal(stripped.get("rail_id"), null);
  });
});

describe("chat about title deep link", () => {
  it("normalizes library_item_id, tmdb, and media_type into a seed", () => {
    const seed = chatAboutTitleSeed({
      title: "The Bear",
      library_item_id: 99,
      tmdb_id: 12345,
      media_type: "show",
      year: 2022,
    });
    assert.equal(seed.title, "The Bear");
    assert.equal(seed.id, 99);
    assert.equal(seed.library_item_id, 99);
    assert.equal(seed.tmdb_id, 12345);
    assert.equal(seed.media_type, "show");
    assert.equal(seed.why, CHAT_ABOUT_TITLE_WHY);
  });

  it("builds a from_rail chat href with discuss opener and stable ids", () => {
    const href = chatAboutTitleHref({
      title: "Heat",
      id: 42,
      year: 1995,
      media_type: "movie",
      rating_key: "rk-heat",
      tmdb_id: 949,
    });
    assert.match(href, /^\/chat\?/);
    assert.match(href, /from_rail=1/);
    assert.match(href, /rail_pack=/);
    assert.match(href, /rail_id=title-42/);
    const params = new URLSearchParams(href.split("?")[1] || "");
    const prompt = chatFromRailPrompt(params);
    assert.match(prompt, /^Let's discuss "Heat"/);
    assert.match(prompt, /library_id=42/);
    assert.match(prompt, /rating_key=rk-heat/);
    assert.match(prompt, /tmdb_id=949/);
    assert.doesNotMatch(prompt, /The curator said: "Let's discuss this"/);
    assert.doesNotMatch(prompt, /from my "Heat" picks/);
  });

  it("falls back to /chat when title is missing", () => {
    assert.equal(chatAboutTitleHref({ media_type: "movie" }), ROUTES.chat);
    assert.equal(chatAboutTitleSeed(null), null);
  });
});

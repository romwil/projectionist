import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  JOURNEY_EYEBROW,
  hasExplorationContent,
  insightBrowseHref,
  insightChatHref,
  personChatHref,
  personExploreHref,
  personShelfLabel,
} from "./journeyExploration.js";

describe("journeyExploration", () => {
  it("uses cinema-map copy without achievement language", () => {
    assert.match(JOURNEY_EYEBROW, /cinema map/i);
    assert.doesNotMatch(JOURNEY_EYEBROW, /achievement/i);
  });

  it("builds person explore and chat deep links", () => {
    const director = { name: "Christopher Nolan", role: "director", count: 6, tmdb_person_id: 525 };
    assert.equal(personExploreHref(director), "/explore?directors=Christopher%20Nolan");
    const chatHref = personChatHref(director);
    assert.match(chatHref, /\/chat\?/);
    const why = new URLSearchParams(chatHref.split("?")[1]).get("rail_why") || "";
    assert.match(why, /work in your shelf/i);
    assert.equal(personShelfLabel(director), "6 in your shelf");
  });

  it("routes cinematographers to person pages when tmdb id is known", () => {
    const dp = { name: "Roger Deakins", role: "cinematographer", tmdb_person_id: 58194, count: 4 };
    assert.equal(personExploreHref(dp), "/person/58194");
  });

  it("builds insight browse and chat links", () => {
    const genre = { id: "genre-noir", kind: "genre", label: "Noir", count: 8, note: "8 titles" };
    assert.equal(insightBrowseHref(genre), "/explore?genre=Noir");
    assert.match(insightChatHref(genre), /\/chat\?/);

    const era = { id: "era-1970s", kind: "era", label: "1970s", count: 12, note: "12 titles" };
    assert.equal(insightBrowseHref(era), "/explore?decade=1970s");
  });

  it("detects when exploration payload has content", () => {
    assert.equal(hasExplorationContent(null), false);
    assert.equal(hasExplorationContent({ people: {}, insights: [], courses: [], explainers: [] }), false);
    assert.equal(
      hasExplorationContent({ people: { directors: [{ name: "A", count: 1 }] }, insights: [], courses: [], explainers: [] }),
      true,
    );
  });
});

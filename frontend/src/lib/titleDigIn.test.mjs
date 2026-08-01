import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  isTitleDetailHref,
  linkifyKnownTitles,
  titleItemFromHref,
  titleRefsFromBlocks,
} from "./titleDigIn.js";

describe("titleItemFromHref", () => {
  it("parses tmdb movie/show paths", () => {
    assert.deepEqual(titleItemFromHref("/title/movie/78"), {
      media_type: "movie",
      tmdb_id: 78,
    });
    assert.deepEqual(titleItemFromHref("/title/show/2199"), {
      media_type: "show",
      tmdb_id: 2199,
    });
  });

  it("parses rating_key and tvdb variants", () => {
    assert.deepEqual(titleItemFromHref("/title/movie/abc%2F1?id_type=rating_key"), {
      media_type: "movie",
      rating_key: "abc/1",
      in_library: true,
    });
    assert.deepEqual(titleItemFromHref("/title/show/12345?id_type=tvdb"), {
      media_type: "show",
      tvdb_id: 12345,
    });
  });

  it("rejects non-title hrefs", () => {
    assert.equal(titleItemFromHref("/explore"), null);
    assert.equal(titleItemFromHref("https://example.com/title/movie/1"), null);
    assert.equal(isTitleDetailHref("/chat"), false);
    assert.equal(isTitleDetailHref("/title/movie/1"), true);
  });
});

describe("linkifyKnownTitles", () => {
  const heat = { title: "Heat", media_type: "movie", tmdb_id: 949 };

  it("wraps bold titles with markdown links", () => {
    assert.equal(
      linkifyKnownTitles("You already own **Heat** in the library.", [heat]),
      "You already own **[Heat](/title/movie/949)** in the library.",
    );
  });

  it("wraps list-item title leads", () => {
    assert.equal(
      linkifyKnownTitles("- Heat\n- Other", [heat]),
      "- [Heat](/title/movie/949)\n- Other",
    );
  });

  it("skips titles already linked", () => {
    const linked = "See [Heat](/title/movie/949) tonight.";
    assert.equal(linkifyKnownTitles(linked, [heat]), linked);
  });
});

describe("titleRefsFromBlocks", () => {
  it("collects title_cards and double_feature refs", () => {
    const refs = titleRefsFromBlocks([
      { type: "text", content: "hi" },
      {
        type: "title_cards",
        items: [{ title: "Heat", media_type: "movie", tmdb_id: 949 }],
      },
      {
        type: "double_feature",
        payload: {
          title_a: { title: "Arrival", media_type: "movie", tmdb_id: 329865 },
          title_b: { title: "Nope", media_type: "movie" },
        },
      },
    ]);
    assert.equal(refs.length, 2);
    assert.equal(refs[0].title, "Heat");
    assert.equal(refs[1].title, "Arrival");
  });
});

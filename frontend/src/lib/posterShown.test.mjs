import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import Poster from "../components/Poster.tsx";
import { cachedPosterMark, loadedPosterMark, posterIsShown } from "./posterShown.ts";

const art = "/api/library/art/movie/348?id_type=tmdb&kind=poster";
const browserSrc = `http://127.0.0.1:8799${art}`;

describe("a relative poster src", () => {
  it("is shown when the load is marked against the art prop", () => {
    assert.equal(loadedPosterMark(art), art);
    assert.notEqual(art, browserSrc);
    assert.equal(posterIsShown(art, loadedPosterMark(art)), true);
    assert.equal(posterIsShown(art, browserSrc), false);
    assert.equal(posterIsShown(art, ""), false);
    assert.equal(posterIsShown("", art), false);
  });

  it("is shown from cache when the image has already decoded", () => {
    assert.equal(cachedPosterMark(art, { complete: true, naturalWidth: 300 }), art);
    assert.equal(posterIsShown(art, cachedPosterMark(art, { complete: true, naturalWidth: 300 })), true);
    assert.equal(cachedPosterMark(art, { complete: false, naturalWidth: 0 }), "");
    assert.equal(cachedPosterMark(art, { complete: true, naturalWidth: 0 }), "");
    assert.equal(cachedPosterMark(art, null), "");
  });

  it("renders the relative address and keeps the picture hidden until it loads", () => {
    const html = renderToStaticMarkup(
      createElement(Poster, { src: art, title: "Alien", year: 1979, itemId: 348 }),
    );
    assert.match(html, /src="\/api\/library\/art\/movie\/348\?id_type=tmdb&amp;kind=poster"/);
    assert.match(html, /class="poster-art"/);
    assert.doesNotMatch(html, /is-shown/);
  });
});

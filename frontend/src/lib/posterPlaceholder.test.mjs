import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { posterMotif, posterPalette, posterSeed } from "./posterPlaceholder.ts";

describe("poster placeholders", () => {
  it("seeds the same item id to the same motif", () => {
    const first = posterSeed("movie-42");
    const again = posterSeed("movie-42");
    assert.equal(first, again);
    assert.equal(posterMotif(first), posterMotif(again));
    assert.notEqual(posterSeed("movie-42"), posterSeed("movie-43"));
  });

  it("builds a duotone from the seed", () => {
    const paint = posterPalette(posterSeed("show-7"));
    assert.match(paint.a, /^hsl\(/);
    assert.match(paint.b, /^hsl\(/);
    assert.notEqual(paint.a, paint.b);
  });
});

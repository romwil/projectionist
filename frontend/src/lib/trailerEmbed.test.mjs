import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";

import { trailerEmbedUrl } from "./trailerEmbed.ts";

const src = join(dirname(fileURLToPath(import.meta.url)), "..");
const trailerSources = [
  ["TitleDetailPage", readFileSync(join(src, "pages", "TitleDetailPage.tsx"), "utf8")],
  ["PosterOverlayControls", readFileSync(join(src, "components", "PosterOverlayControls.tsx"), "utf8")],
  ["TitleDetailDrawer", readFileSync(join(src, "components", "TitleDetailDrawer.tsx"), "utf8")],
];

describe("YouTube trailer embeds", () => {
  it("uses the privacy-enhanced player and never autoplays (A11Y-005)", () => {
    const url = trailerEmbedUrl("abc123");
    assert.ok(url.startsWith("https://www.youtube-nocookie.com/embed/abc123"));
    assert.ok(!/autoplay/.test(url));
    assert.ok(trailerEmbedUrl("a b").includes("/embed/a%20b"));
  });

  for (const [name, source] of trailerSources) {
    it(`${name} builds its embed from the shared helper with explicit permissions and fallback`, () => {
      assert.match(source, /src=\{trailerEmbedUrl\(trailerKey\)\}/);
      assert.match(source, /ref=\{focusTrailerFrame\}/);
      assert.doesNotMatch(source, /autoplay=1/);
      assert.match(source, /allow="[^"]*autoplay[^"]*encrypted-media[^"]*picture-in-picture[^"]*fullscreen/);
      assert.match(source, /referrerPolicy="strict-origin-when-cross-origin"/);
      assert.match(source, /Open on YouTube/);
    });
  }
});

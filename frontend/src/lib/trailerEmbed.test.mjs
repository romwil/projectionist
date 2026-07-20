import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";

const src = join(dirname(fileURLToPath(import.meta.url)), "..");
const trailerSources = [
  readFileSync(join(src, "pages", "TitleDetailPage.jsx"), "utf8"),
  readFileSync(join(src, "components", "PosterOverlayControls.jsx"), "utf8"),
];

describe("YouTube trailer embeds", () => {
  for (const source of trailerSources) {
    it("uses the privacy-enhanced player with explicit permissions and fallback", () => {
      assert.match(source, /https:\/\/www\.youtube-nocookie\.com\/embed\//);
      assert.match(source, /allow="[^"]*autoplay[^"]*encrypted-media[^"]*picture-in-picture[^"]*fullscreen/);
      assert.match(source, /referrerPolicy="strict-origin-when-cross-origin"/);
      assert.match(source, /Open on YouTube/);
    });
  }
});

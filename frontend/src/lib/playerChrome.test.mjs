import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const watchCss = readFileSync(join(root, "../styles/13-watch.css"), "utf8");
const playerSrc = readFileSync(join(root, "../components/theater/LibraryPlayer.jsx"), "utf8");

const marker = "/*\n * lights-up-player-chrome";
const lightsUp = watchCss.slice(watchCss.indexOf(marker));

describe("Play controls follow Lights Up", () => {
  it("does not lock the round controls to a dark-only fill", () => {
    assert.ok(lightsUp.length > 200, "expected lights-up-player-chrome block");
    assert.match(lightsUp, /html\[data-theme="lights-up"\] \.theater-osd-secondary/);
    const secondary = lightsUp.match(
      /html\[data-theme="lights-up"\] \.theater-osd-secondary\s*\{([^}]+)\}/,
    );
    assert.ok(secondary, "missing lights-up secondary control rule");
    assert.match(secondary[1], /var\(--text\)/);
    assert.match(secondary[1], /var\(--surface-2\)/);
    assert.match(secondary[1], /var\(--border\)/);
    assert.doesNotMatch(secondary[1], /#(?:fff|ffffff|e6e2d6|1a1200)/i);
    assert.doesNotMatch(secondary[1], /rgba\(\s*255\s*,\s*255\s*,\s*255/);
    assert.match(watchCss, /\.theater-osd-play\s*\{[^}]*background:\s*var\(--accent\)/);
    assert.match(watchCss, /\.theater-osd-play\s*\{[^}]*color:\s*var\(--accent-text\)/);
  });
});

describe("Play ±30 controls", () => {
  it("renders ±30 through the same skip path and hides them unless the bar is wide", () => {
    assert.match(playerSrc, /skipBy\(-SKIP_LONG_SECONDS\)/);
    assert.match(playerSrc, /skipBy\(SKIP_LONG_SECONDS\)/);
    assert.match(playerSrc, /skipBy\(-SKIP_SECONDS\)/);
    assert.match(playerSrc, /skipBy\(SKIP_SECONDS\)/);
    assert.match(playerSrc, /data-long-skip=\{longSkip \? "true" : "false"\}/);
    assert.match(playerSrc, /longSkip \?/);
    assert.match(watchCss, /\.theater-osd-skip-long\s*\{\s*display:\s*none;/);
    assert.match(
      watchCss,
      /\.library-watch\[data-long-skip="true"\] \.theater-osd-skip-long\s*\{\s*display:\s*inline-flex;/,
    );
    assert.doesNotMatch(playerSrc, /\.setPointerCapture/);
    assert.match(watchCss, /\.theater-scrubber-row\s*\{[^}]*touch-action:\s*manipulation/);
  });
});

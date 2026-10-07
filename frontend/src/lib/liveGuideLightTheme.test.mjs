import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const cssPath = join(dirname(fileURLToPath(import.meta.url)), "../styles/12-live.css");
const css = readFileSync(cssPath, "utf8");
const marker = "/*\n * lights-up-live-surfaces";
const lightsUp = css.slice(css.indexOf(marker));

const DARK_CHAMBER = /#07080c|#050608|#100e0c|#f4efe4|#ffb800|rgba\(\s*8\s*,\s*9\s*,\s*14|rgba\(\s*28\s*,\s*32\s*,\s*41|rgba\(\s*16\s*,\s*18\s*,\s*24|rgba\(\s*40\s*,\s*34\s*,\s*20|rgba\(\s*230\s*,\s*226\s*,\s*214/;

function ruleBody(source, selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = source.match(new RegExp(`${escaped}\\s*\\{([^}]+)\\}`));
  assert.ok(match, `missing rule ${selector}`);
  return match[1];
}

describe("live guide and weather follow Lights Up tokens", () => {
  it("keeps a Lights Up block that is not a second dark palette", () => {
    assert.ok(lightsUp.length > 400, "expected lights-up-live-surfaces block");
    assert.doesNotMatch(lightsUp, DARK_CHAMBER);
    assert.match(lightsUp, /var\(--bg\)/);
    assert.match(lightsUp, /var\(--surface\)/);
    assert.match(lightsUp, /var\(--surface-raised\)/);
    assert.match(lightsUp, /var\(--text\)/);
    assert.match(lightsUp, /var\(--muted\)/);
    assert.match(lightsUp, /var\(--accent-2\)/);
    assert.match(lightsUp, /var\(--border\)/);
  });

  it("unlocks the guide page, grid, and programme card from the dark chamber", () => {
    const page = ruleBody(
      lightsUp,
      `html[data-theme="lights-up"] .live-page--guide,
html[data-theme="lights-up"] .live-page--empty,
html[data-theme="lights-up"] .live-page--watch:has(.weather-channel)`,
    );
    assert.match(page, /--live-bg:\s*var\(--bg\)/);
    assert.match(page, /--live-line:\s*var\(--border-subtle\)/);
    assert.doesNotMatch(page, /#07080c|#12151c|#050608/);

    const rail = ruleBody(
      lightsUp,
      `html[data-theme="lights-up"] .live-guide-rail,
html[data-theme="lights-up"] .live-guide-rail-corner,
html[data-theme="lights-up"] .live-guide-timeline`,
    );
    assert.match(rail, /background:\s*var\(--surface\)/);
    assert.match(rail, /color:\s*var\(--text\)/);

    const rows = ruleBody(lightsUp, `html[data-theme="lights-up"] .live-guide-rows`);
    assert.match(rows, /var\(--border\)/);
    assert.match(rows, /var\(--border-subtle\)/);
    assert.doesNotMatch(rows, /rgba\(\s*230\s*,\s*226\s*,\s*214/);

    const cell = ruleBody(lightsUp, `html[data-theme="lights-up"] .live-guide-cell`);
    assert.match(cell, /background:\s*var\(--surface-raised\)/);
    assert.match(cell, /color:\s*var\(--text\)/);
    assert.match(cell, /border-color:\s*var\(--border\)/);

    const hover = ruleBody(
      lightsUp,
      `html[data-theme="lights-up"] .live-guide-cell:hover,
html[data-theme="lights-up"] .live-guide-cell.is-focused`,
    );
    assert.match(hover, /var\(--accent-soft\)/);
    assert.match(hover, /border-color:\s*var\(--accent-2\)/);
    assert.match(hover, /color:\s*var\(--text\)/);
    assert.doesNotMatch(hover, /rgba\(\s*40\s*,\s*34\s*,\s*20/);

    const now = ruleBody(lightsUp, `html[data-theme="lights-up"] .live-guide-now-line`);
    assert.match(now, /background:\s*var\(--accent-2\)/);

    const card = ruleBody(lightsUp, `html[data-theme="lights-up"] .live-program-hover`);
    assert.match(card, /background:\s*var\(--surface-raised\)/);
    assert.match(card, /color:\s*var\(--text\)/);
    assert.doesNotMatch(card, /rgba\(\s*16\s*,\s*18\s*,\s*24/);
  });

  it("paints the weather board, ticker, and corner controls with theme tokens", () => {
    const board = ruleBody(lightsUp, `html[data-theme="lights-up"] .weather-channel`);
    assert.match(board, /--wx-ink:\s*var\(--text\)/);
    assert.match(board, /--wx-amber:\s*var\(--accent-2\)/);
    assert.match(board, /--wx-dim:\s*var\(--muted\)/);
    assert.match(board, /background:\s*var\(--bg\)/);
    assert.match(board, /color:\s*var\(--text\)/);
    assert.doesNotMatch(board, /#100e0c|#f4efe4|#ffb800/);

    const sky = ruleBody(
      lightsUp,
      `html[data-theme="lights-up"] .weather-channel .weather-channel-sky`,
    );
    assert.match(sky, /var\(--bg\)/);
    assert.match(sky, /var\(--workspace-wash-a\)/);
    assert.doesNotMatch(sky, /#100e0c|#0a0908|#14110d/);

    const frames = ruleBody(lightsUp, `html[data-theme="lights-up"] .weather-channel .ghost`);
    assert.match(frames, /background:\s*var\(--surface-raised\)/);
    assert.match(frames, /border-color:\s*var\(--border\)/);
    assert.match(frames, /color:\s*var\(--text\)/);

    const ticker = ruleBody(lightsUp, `html[data-theme="lights-up"] .weather-channel-ticker`);
    assert.match(ticker, /background:\s*var\(--surface-2\)/);
    assert.match(ticker, /color:\s*var\(--text\)/);
    assert.match(ticker, /border-color:\s*var\(--border\)/);
  });

  it("leaves the Lights Down guide and weather board on the dark chamber", () => {
    const before = css.slice(0, css.indexOf(marker));
    assert.match(ruleBody(before, ".live-page"), /#07080c/);
    assert.match(ruleBody(before, ".live-guide-rail"), /rgba\(8,\s*9,\s*14,\s*0\.96\)/);
    assert.match(ruleBody(before, ".live-guide-cell"), /rgba\(28,\s*32,\s*41,\s*0\.92\)/);
    assert.match(ruleBody(before, ".live-program-hover"), /rgba\(16,\s*18,\s*24,\s*0\.97\)/);
    assert.match(ruleBody(before, ".weather-channel"), /#100e0c/);
    assert.match(ruleBody(before, ".weather-channel"), /--wx-ink:\s*#f4efe4/);
    assert.doesNotMatch(before, /html\[data-theme="lights-up"\]/);
  });
});

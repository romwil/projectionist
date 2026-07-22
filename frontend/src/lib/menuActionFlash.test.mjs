import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

describe("kebab action flash", () => {
  it("styles a high-contrast menu-action-flash toast", () => {
    const css = readFileSync(join(root, "styles/07-persona-editorial.css"), "utf8");
    assert.match(css, /\.menu-action-flash\s*\{/);
    assert.match(css, /font-weight:\s*600/);
    assert.match(css, /color:\s*var\(--text\)/);
  });

  it("ShareActionMenu flashes confirmation outside the open menu", () => {
    const src = readFileSync(join(root, "components/ShareActionMenu.jsx"), "utf8");
    assert.match(src, /data-testid="share-action-flash"/);
    assert.match(src, /Library link copied\./);
    assert.match(src, /showFlash\(/);
    assert.match(src, /setOpen\(false\)/);
    assert.doesNotMatch(src, /share-action-status/);
  });

  it("PosterActionMenu uses the same flash toast pattern", () => {
    const src = readFileSync(join(root, "components/PosterActionMenu.jsx"), "utf8");
    assert.match(src, /data-testid="poster-action-flash"/);
    assert.match(src, /flashStatus\(/);
    assert.doesNotMatch(src, /poster-action-status/);
  });
});

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const styles = readFileSync(join(root, "styles.css"), "utf8");

describe("explore and recommendations responsive layout", () => {
  it("contains explore page overflow and local poster-rail scrolling", () => {
    assert.match(styles, /\.explore-page\s*\{[^}]*overflow-x:\s*clip/s);
    assert.match(styles, /\.explore-card-rail\s*\{[^}]*max-width:\s*100%/s);
    assert.match(styles, /\.explore-card-rail\s*\{[^}]*overflow-x:\s*auto/s);
    assert.match(styles, /\.explore-motif-chips\s*\{[^}]*flex-wrap:\s*wrap/s);
    assert.match(styles, /\.explore-motif-chips-scroll\s*\{[^}]*max-height:/s);
    assert.match(styles, /\.explore-motif-chips-scroll\s*\{[^}]*overflow-y:\s*auto/s);
    assert.match(styles, /\.explore-motif-chip\s*\{[^}]*max-width:\s*100%/s);
    assert.match(styles, /\.explore-section\s*\{[^}]*min-width:\s*0/s);
  });

  it("keeps explore section multi-select toolbar inside the reading column", () => {
    assert.match(styles, /\.explore-section-toolbar\s*\{[^}]*width:\s*min\(var\(--reading-column-max/s);
    assert.match(styles, /\.explore-section-toolbar\s*\{[^}]*overflow-x:\s*clip/s);
    assert.match(styles, /\.explore-section-bulk\s*\{[^}]*flex-wrap:\s*wrap/s);
    assert.match(styles, /\.explore-section-sort select\s*\{[^}]*border:\s*1px solid var\(--border/s);
  });

  it("keeps poster hover actions as corner icons on the poster", () => {
    assert.match(styles, /\.explore-poster\s*\{[^}]*position:\s*relative/s);
    assert.match(
      styles,
      /\.explore-hover-icon-watch\s*\{[^}]*top:\s*50%;[^}]*left:\s*50%;[^}]*transform:\s*translate\(-50%,\s*-50%\)/s,
    );
    assert.match(styles, /\.explore-hover-icon-trailer\s*\{[^}]*right:/s);
    assert.match(styles, /\.explore-hover-icon-recommend\s*\{[^}]*bottom:/s);
    assert.doesNotMatch(styles, /\.explore-card-hover-actions\s*\{[^}]*bottom:\s*3\.4rem/s);
  });

  it("makes the recommendations viewport fill width instead of a left-heavy column track", () => {
    assert.match(
      styles,
      /\.viewport \.turnstyle-track\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fit/s,
    );
    assert.match(styles, /\.viewport \.turnstyle-track\s*\{[^}]*grid-auto-flow:\s*row/s);
    assert.match(styles, /\.viewport \.title-card\s*\{[^}]*min-width:\s*0/s);
    assert.match(styles, /\.viewport \.title-card \.overview\s*\{[^}]*-webkit-line-clamp:\s*4/s);
  });
});

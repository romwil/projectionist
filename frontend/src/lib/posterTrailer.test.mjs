import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";
import {
  NO_TRAILER_TOAST,
  TRAILER_REQUEST_FAILED_TOAST,
  posterTrailerRequestPath,
  trailerLookupOutcome,
} from "./posterTrailer.ts";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

describe("poster trailer lookup", () => {
  it("clears busy state and toasts when the title has no trailer", () => {
    const outcome = trailerLookupOutcome({ detail: { title: "Unchained Reaction", trailer_youtube_key: "" } });
    assert.equal(outcome.loading, false);
    assert.equal(outcome.open, false);
    assert.equal(outcome.key, "");
    assert.equal(outcome.toast, NO_TRAILER_TOAST);
    assert.equal(outcome.toast, "No trailer for this title.");
  });

  it("opens a real trailer without a toast", () => {
    const outcome = trailerLookupOutcome({ detail: { trailer_youtube_key: "dQw4w9WgXcQ" } });
    assert.equal(outcome.loading, false);
    assert.equal(outcome.open, true);
    assert.equal(outcome.key, "dQw4w9WgXcQ");
    assert.equal(outcome.toast, "");
  });

  it("toasts a failed request separately from a missing trailer", () => {
    const outcome = trailerLookupOutcome({ error: new Error("TMDB timed out") });
    assert.equal(outcome.loading, false);
    assert.equal(outcome.open, false);
    assert.equal(outcome.toast, "TMDB timed out");
    assert.notEqual(outcome.toast, NO_TRAILER_TOAST);

    const blank = trailerLookupOutcome({ error: new Error("  ") });
    assert.equal(blank.loading, false);
    assert.equal(blank.toast, TRAILER_REQUEST_FAILED_TOAST);
    assert.notEqual(blank.toast, NO_TRAILER_TOAST);
  });

  it("does not look up a card with no title identity", () => {
    assert.equal(posterTrailerRequestPath({ title: "Untitled" }), null);
    assert.equal(
      posterTrailerRequestPath({ media_type: "movie", tmdb_id: 42 }),
      "/title/movie/42?id_type=tmdb&enrich=1",
    );
  });

  it("poster control uses the shared menu-action-flash toast in both themes", () => {
    const overlay = readFileSync(join(root, "components/PosterOverlayControls.tsx"), "utf8");
    const css = readFileSync(join(root, "styles/07-persona-editorial.css"), "utf8");
    const tokens = readFileSync(join(root, "styles/01-tokens.css"), "utf8");
    assert.match(overlay, /trailerLookupOutcome/);
    assert.match(overlay, /setTrailerLoading\(false\)/);
    assert.match(overlay, /className="menu-action-flash"/);
    assert.match(css, /\.menu-action-flash\s*\{[^}]*color:\s*var\(--text\)/s);
    assert.match(css, /\.menu-action-flash\s*\{[^}]*background:\s*var\(--surface-raised/s);
    assert.match(tokens, /html\[data-theme="lights-down"\][\s\S]*?--text:\s*#e6e2d6/);
    assert.match(tokens, /html\[data-theme="lights-up"\][\s\S]*?--text:\s*#1b1c19/);
    assert.match(tokens, /html\[data-theme="lights-down"\][\s\S]*?--surface-raised:\s*#1c2029/);
    assert.match(tokens, /html\[data-theme="lights-up"\][\s\S]*?--surface-raised:\s*#ffffff/);
  });
});

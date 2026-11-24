import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { installableCacheDecision } from "../../public/installable-cache.mjs";

const origin = "http://household.local";
const here = dirname(fileURLToPath(import.meta.url));

describe("installable cache policy", () => {
  it("stores the app shell and static assets", () => {
    assert.equal(
      installableCacheDecision(`${origin}/assets/index-abc.js`, "GET", origin),
      "static",
    );
    assert.equal(installableCacheDecision(`${origin}/offline.html`, "GET", origin), "static");
    assert.equal(installableCacheDecision(`${origin}/icon-512.png`, "GET", origin), "static");
    assert.equal(installableCacheDecision("/favicon.svg", "GET", origin), "static");
  });

  it("never stores API, art, or media", () => {
    const blocked = [
      `${origin}/api/features`,
      `${origin}/api/library/art/movie/1?kind=poster`,
      `${origin}/api/playback/sessions/abc/master.m3u8`,
      `${origin}/api/playback/sessions/abc/seg-1.m4s`,
      `${origin}/watch/12345`,
      `${origin}/playback/session/playlist.m3u8`,
      `${origin}/library/art/poster.jpg`,
      `${origin}/captions/film.vtt`,
      "https://other.example/assets/app.js",
    ];
    for (const url of blocked) {
      assert.equal(installableCacheDecision(url, "GET", origin), "bypass", url);
      assert.equal(installableCacheDecision(url, "POST", origin), "bypass", url);
    }
  });

  it("refuses a disguised API path and a null byte", () => {
    assert.equal(installableCacheDecision(`${origin}/api%2Ffeatures`, "GET", origin), "bypass");
    assert.equal(
      installableCacheDecision(`${origin}/assets/../api/health`, "GET", origin),
      "bypass",
    );
    assert.equal(installableCacheDecision(`${origin}/assets/%00.js`, "GET", origin), "bypass");
  });

  it("the service worker asks this policy before it stores anything", () => {
    const worker = readFileSync(join(here, "../../public/sw.js"), "utf8");
    assert.match(worker, /installableCacheDecision/);
    assert.match(worker, /decision !== "static"/);
    assert.doesNotMatch(worker, /caches\.put\([\s\S]*\/api/);
    assert.match(worker, /offline\.html/);
  });
});

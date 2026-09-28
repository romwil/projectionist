import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { aboutHashTargetId, scrollAboutHashIntoView } from "./aboutHashScroll.js";

const here = dirname(fileURLToPath(import.meta.url));
const aboutPage = readFileSync(join(here, "../pages/AboutPage.jsx"), "utf8");

describe("about hash scroll", () => {
  it("maps #license and #release-notes and ignores other hashes", () => {
    assert.equal(aboutHashTargetId("#license"), "license");
    assert.equal(aboutHashTargetId("license"), "license");
    assert.equal(aboutHashTargetId("#release-notes"), "release-notes");
    assert.equal(aboutHashTargetId("#story"), "");
    assert.equal(aboutHashTargetId(""), "");
    assert.equal(aboutHashTargetId(null), "");
  });

  it("scrolls the license node when hash is #license", () => {
    const calls = [];
    const nodes = {
      license: { scrollIntoView: () => calls.push("license") },
      "release-notes": { scrollIntoView: () => calls.push("release-notes") },
    };
    assert.equal(
      scrollAboutHashIntoView("#license", (id) => nodes[id] || null),
      true,
    );
    assert.deepEqual(calls, ["license"]);
  });

  it("scrolls release notes when hash is #release-notes", () => {
    const calls = [];
    const node = { scrollIntoView: () => calls.push("release-notes") };
    assert.equal(
      scrollAboutHashIntoView("#release-notes", (id) => (id === "release-notes" ? node : null)),
      true,
    );
    assert.deepEqual(calls, ["release-notes"]);
  });

  it("does not scroll when the hash is unknown or the node is missing", () => {
    const calls = [];
    const license = { scrollIntoView: () => calls.push("license") };
    assert.equal(scrollAboutHashIntoView("#story", (id) => (id === "license" ? license : null)), false);
    assert.equal(scrollAboutHashIntoView("#license", () => null), false);
    assert.equal(scrollAboutHashIntoView("#license", () => ({})), false);
    assert.deepEqual(calls, []);
  });

  it("wires About sections and the helper after AppShell authReady", () => {
    assert.match(aboutPage, /id="license"/);
    assert.match(aboutPage, /id="release-notes"/);
    assert.match(aboutPage, /function AboutHashScroller/);
    assert.match(aboutPage, /scrollAboutHashIntoView\(hash\)/);
    assert.match(aboutPage, /<AboutHashScroller \/>/);
  });
});

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { decadeYearRange, exploreCountryPath, exploreDecadePath } from "./browseLinks.js";
import {
  countryBrowsePath,
  decadeBrowsePath,
  decadeLabel,
  languageBrowseMeta,
} from "./titleDetailMeta.js";

describe("titleDetailMeta", () => {
  it("builds decade labels and browse paths", () => {
    assert.equal(decadeLabel(2026), "2020s");
    assert.equal(decadeBrowsePath(2026), "/explore?decade=2020s");
    assert.equal(exploreDecadePath("2020s"), "/explore?decade=2020s");
    assert.deepEqual(decadeYearRange("2020s"), { year_from: 2020, year_to: 2029 });
  });

  it("links language to a relative Explore language landing", () => {
    assert.deepEqual(languageBrowseMeta("en"), {
      label: "English",
      path: "/explore?language=en",
    });
    assert.deepEqual(languageBrowseMeta("en-US"), {
      label: "English",
      path: "/explore?language=en",
    });
    assert.deepEqual(languageBrowseMeta("hi"), {
      label: "Hindi",
      path: "/explore?language=hi",
    });
    assert.equal(languageBrowseMeta("en").path.startsWith("/explore?language="), true);
    assert.equal(languageBrowseMeta("en").path.includes("automat.vip"), false);
    assert.equal(languageBrowseMeta(""), null);
    assert.equal(languageBrowseMeta(null), null);
  });

  it("builds country browse paths", () => {
    assert.equal(countryBrowsePath("India"), "/explore?country=India");
    assert.equal(exploreCountryPath("United Kingdom"), "/explore?country=United%20Kingdom");
  });
});

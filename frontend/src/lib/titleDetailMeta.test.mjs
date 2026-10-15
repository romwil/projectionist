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

  it("shows language as a label and does not link to Explore", () => {
    for (const code of ["en", "EN", "en-US", "hi"]) {
      const meta = languageBrowseMeta(code);
      assert.equal(typeof meta.label, "string");
      assert.ok(meta.label.length > 0);
      assert.equal("path" in meta, false);
      const serialized = JSON.stringify(meta);
      assert.equal(serialized.includes("/explore?language="), false);
      assert.equal(serialized.includes("automat.vip"), false);
    }
    assert.deepEqual(languageBrowseMeta("en"), { label: "English" });
    assert.deepEqual(languageBrowseMeta("hi"), { label: "Hindi" });
    assert.equal(languageBrowseMeta(""), null);
    assert.equal(languageBrowseMeta(null), null);
  });

  it("builds country browse paths", () => {
    assert.equal(countryBrowsePath("India"), "/explore?country=India");
    assert.equal(exploreCountryPath("United Kingdom"), "/explore?country=United%20Kingdom");
  });
});

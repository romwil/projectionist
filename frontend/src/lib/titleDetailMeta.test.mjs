import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { decadeYearRange, exploreCountryPath, exploreDecadePath, exploreLanguagePath } from "./browseLinks.js";
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

  it("builds language browse meta with stable facet keys", () => {
    assert.deepEqual(languageBrowseMeta("hi"), {
      label: "Hindi",
      path: "/explore?language=hi",
    });
    assert.equal(exploreLanguagePath("HI"), "/explore?language=hi");
  });

  it("builds country browse paths", () => {
    assert.equal(countryBrowsePath("India"), "/explore?country=India");
    assert.equal(exploreCountryPath("United Kingdom"), "/explore?country=United%20Kingdom");
  });
});

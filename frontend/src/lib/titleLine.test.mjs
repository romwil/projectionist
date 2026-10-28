import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { readAllStyles } from "./readStyles.mjs";
import {
  mediaYear,
  titleAlreadyHasYear,
  titleLineParts,
  titleWithYear,
} from "./titleLine.ts";

const srcRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const styles = readAllStyles();

const CARD_SURFACES = [
  "components/LibraryMediaCard.tsx",
  "components/TitleNeighborsRails.tsx",
  "components/TitleCard.tsx",
  "pages/RelatedTitlesPage.tsx",
  "lib/liveProgramDetail.ts",
];

describe("titleLine helper", () => {
  it("puts year inline after the title", () => {
    assert.equal(
      titleWithYear({ title: "The Last House on the Left", year: 2009 }),
      "The Last House on the Left (2009)",
    );
    assert.equal(
      titleWithYear({ title: "Heat", year: "1995" }),
      "Heat (1995)",
    );
    assert.deepEqual(titleLineParts({ title: "Heat", year: 1995 }), {
      title: "Heat",
      year: 1995,
      label: "Heat (1995)",
    });
  });

  it("omits year when missing or unusable", () => {
    assert.equal(titleWithYear({ title: "Heat" }), "Heat");
    assert.equal(titleWithYear({ title: "Heat", year: null }), "Heat");
    assert.equal(titleWithYear({ title: "Heat", year: "" }), "Heat");
    assert.equal(titleWithYear({ title: "Heat", year: "tba" }), "Heat");
    assert.equal(titleWithYear({ title: "Heat", year: 0 }), "Heat");
    assert.equal(titleWithYear(null), "Untitled");
    assert.equal(titleWithYear({}, { fallback: "Untitled" }), "Untitled");
    assert.equal(mediaYear("1995"), 1995);
    assert.equal(mediaYear(1995.9), 1995);
    assert.equal(mediaYear("nope"), null);
  });

  it("does not double a title that already contains a year", () => {
    assert.equal(
      titleWithYear({ title: "The Last House on the Left (2009)", year: 2009 }),
      "The Last House on the Left (2009)",
    );
    assert.equal(
      titleWithYear({ title: "Heat (1995)", year: 1995 }),
      "Heat (1995)",
    );
    assert.equal(
      titleWithYear({ title: "Alien (1979)" }),
      "Alien (1979)",
    );
    assert.equal(
      titleWithYear({ title: "Foo (1977)", year: 2009 }),
      "Foo (1977)",
    );
    assert.equal(titleAlreadyHasYear("Heat (1995)", 1995), true);
    assert.equal(titleAlreadyHasYear("2012", 2009), false);
    assert.equal(
      titleWithYear({ title: "2012", year: 2009 }),
      "2012 (2009)",
    );
    assert.equal(
      titleWithYear({ title: "Blade Runner 2049", year: 2017 }),
      "Blade Runner 2049 (2017)",
    );
  });
});

describe("title-line card surfaces", () => {
  it("uses the shared helper instead of a sibling year block", () => {
    for (const rel of CARD_SURFACES) {
      const src = readFileSync(join(srcRoot, rel), "utf8");
      assert.match(
        src,
        /titleWithYear|TitleYearText|titleLineParts/,
        `${rel} should use the shared title-line helper`,
      );
      assert.doesNotMatch(
        src,
        /<p className="(?:explore-card-meta|title-neighbor-year|relation-card-year)">\{[^}]*year/,
        `${rel} must not render year as its own block`,
      );
    }
  });

  it("keeps year in the same wrapping flow (no nowrap / block year)", () => {
    assert.match(styles, /\.title-line-year\b/);
    const yearRule = styles.match(/\.title-line-year\s*\{[^}]*\}/);
    assert.ok(yearRule, "expected .title-line-year rule");
    assert.doesNotMatch(yearRule[0], /white-space:\s*nowrap/);
    assert.doesNotMatch(yearRule[0], /display:\s*block/);
  });
});

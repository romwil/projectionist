import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  sonarrFindMissingButtonClass,
  sonarrMissingBySeries,
  sonarrMissingPhaseLabel,
  sonarrMissingProgressLine,
  sonarrMissingScanReady,
  sonarrSearchMissingButtonClass,
  sonarrWantedDeltaCopy,
} from "./sonarrMissing.js";

const here = dirname(fileURLToPath(import.meta.url));
const configPage = readFileSync(join(here, "../pages/ConfigPage.jsx"), "utf8");
const client = readFileSync(join(here, "../api/client.js"), "utf8");
const help = readFileSync(join(here, "../../../docs/HELP.md"), "utf8");

describe("sonarr find-all-missing helpers", () => {
  it("formats Wanted delta copy from scan vs Wanted counts", () => {
    assert.equal(
      sonarrWantedDeltaCopy({ scan_count: 12, wanted_count: 9 }),
      "Library scan found 12; Sonarr Wanted lists 9",
    );
    assert.equal(
      sonarrWantedDeltaCopy({ summary: "Library scan found 2; Sonarr Wanted lists 2" }),
      "Library scan found 2; Sonarr Wanted lists 2",
    );
  });

  it("keeps one gold primary: Find all missing until scan, then Search these", () => {
    const idle = { phase: "idle", busy: false, result: null };
    assert.equal(sonarrFindMissingButtonClass(idle), "primary");
    assert.equal(sonarrSearchMissingButtonClass(idle), "ghost");
    assert.equal(sonarrMissingScanReady(idle), false);

    const done = {
      phase: "done",
      busy: false,
      result: { scan_count: 4, by_series: [{ seriesId: 1, seriesTitle: "Lost", count: 4, episodes: [] }] },
    };
    assert.equal(sonarrFindMissingButtonClass(done), "ghost");
    assert.equal(sonarrSearchMissingButtonClass(done), "primary");
    assert.equal(sonarrMissingScanReady(done), true);

    const empty = { phase: "done", busy: false, result: { scan_count: 0, episode_ids: [] } };
    assert.equal(sonarrMissingScanReady(empty), false);
    assert.equal(sonarrFindMissingButtonClass(empty), "primary");
    assert.equal(sonarrSearchMissingButtonClass(empty), "ghost");
  });

  it("builds progress from phase, series counts, and missing found", () => {
    const line = sonarrMissingProgressLine({
      phase: "scanning",
      message: "Scanning Lost…",
      series_done: 3,
      series_total: 10,
      missing_found: 7,
    });
    assert.match(line, /Scanning Lost/);
    assert.match(line, /Series 3 of 10/);
    assert.match(line, /7 missing/);
  });

  it("humanizes job phases instead of snake_case keys", () => {
    assert.equal(sonarrMissingPhaseLabel("scanning"), "Scanning series");
    assert.equal(sonarrMissingPhaseLabel("comparing"), "Comparing to Wanted");
    assert.equal(sonarrMissingPhaseLabel("searched"), "Searches queued");
  });

  it("groups missing-by-series for the collapsible summary", () => {
    const groups = sonarrMissingBySeries({
      by_series: [
        { seriesId: 3, seriesTitle: "The Wire", count: 1, episodes: [{ episodeId: 31 }] },
        { seriesId: 1, seriesTitle: "Lost", count: 2, episodes: [{ episodeId: 11 }, { episodeId: 10 }] },
      ],
    });
    assert.equal(groups.length, 2);
    assert.equal(groups[0].seriesTitle, "The Wire");
    assert.equal(groups[1].count, 2);
  });
});

describe("sonarr find-all-missing Admin Libraries card", () => {
  it("exposes the Libraries card, scan, search, and specials toggle", () => {
    assert.match(configPage, /data-testid="sonarr-find-missing-card"/);
    assert.match(configPage, /data-testid="sonarr-find-missing-button"/);
    assert.match(configPage, /data-testid="sonarr-search-missing-button"/);
    assert.match(configPage, /data-testid="sonarr-include-specials"/);
    assert.match(configPage, /Find all missing/);
    assert.match(configPage, /Search these/);
    assert.match(configPage, /Include specials/);
  });

  it("mirrors radarr register-existing client helpers", () => {
    assert.match(client, /export async function startSonarrMissingScan/);
    assert.match(client, /\/admin\/sonarr\/missing\/scan/);
    assert.match(client, /export async function getSonarrMissingStatus/);
    assert.match(client, /export async function searchSonarrMissing/);
  });

  it("HELP explains Wanted vs library scan and rate limits", () => {
    assert.match(help, /Find all missing/);
    assert.match(help, /Wanted/i);
    assert.match(help, /EpisodeSearch/);
    assert.match(help, /rate-limit/i);
  });
});

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  formatEpisodeCode,
  formatSeasonLabel,
  formatShowBytes,
  normalizeShowSeasonsPayload,
  showSeasonsSummaryLine,
} from "./showSeasons.js";

describe("showSeasons helpers", () => {
  it("formats episode codes and season labels", () => {
    assert.equal(formatEpisodeCode(1, 2), "S01E02");
    assert.equal(formatSeasonLabel(0), "Specials");
    assert.equal(formatSeasonLabel(3), "Season 3");
    assert.equal(formatSeasonLabel(null), "Specials");
  });

  it("normalizes seasons payload and summary line", () => {
    const data = normalizeShowSeasonsPayload({
      show_id: 9,
      show_title: "The Expanse",
      total_seasons: 1,
      total_episodes: 2,
      file_size_bytes: 1024 ** 3,
      seasons: [
        {
          season_number: 1,
          episode_count: 2,
          watched_count: 1,
          file_size_bytes: 1024 ** 3,
          episodes: [
            {
              id: 1,
              rating_key: "ep-1",
              season_number: 1,
              episode_number: 1,
              title: "Dulcinea",
              view_count: 1,
              file_size: 500,
            },
            {
              id: 2,
              rating_key: "ep-2",
              season_number: 1,
              episode_number: 2,
              title: "The Big Empty",
              view_count: 0,
              file_size: 500,
            },
          ],
        },
      ],
    });
    assert.equal(data.seasons[0].episodes.length, 2);
    assert.equal(data.seasons[0].episodes[1].unwatched, true);
    assert.equal(showSeasonsSummaryLine(data), "1 season · 2 episodes · 1.0 GB");
    assert.equal(formatShowBytes(0), "");
  });
});

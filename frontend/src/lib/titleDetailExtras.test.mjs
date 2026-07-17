import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  canMarkTitleWatched,
  filterCollectionPeers,
  formatTitleReleaseBadge,
  formatTvProgress,
  isTitleWatched,
  reviewsCtaForDetail,
  watchedCtaLabel,
} from "./titleDetailExtras.js";

describe("titleDetailExtras", () => {
  it("formats release badge as YYYY Month D or year-only", () => {
    assert.equal(
      formatTitleReleaseBadge({
        releaseDate: "2026-07-10",
        year: 2026,
        mediaType: "movie",
      }),
      "2026 July 10",
    );
    assert.equal(
      formatTitleReleaseBadge({
        firstAirDate: "2011-04-17",
        year: 2011,
        mediaType: "show",
      }),
      "2011 April 17",
    );
    assert.equal(
      formatTitleReleaseBadge({ releaseDate: "2026-07-10", year: 2025, mediaType: "movie" }),
      "2026 July 10",
    );
    assert.equal(formatTitleReleaseBadge({ year: 1999, mediaType: "movie" }), "1999");
    assert.equal(formatTitleReleaseBadge({ releaseDate: "1999", mediaType: "movie" }), "1999");
    assert.equal(formatTitleReleaseBadge({ mediaType: "movie" }), null);
  });

  it("formats TV progress when episode counts exist", () => {
    assert.deepEqual(formatTvProgress({ total_episode_count: 10, unwatched_episode_count: 3 }), {
      total: 10,
      unwatched: 3,
      watched: 7,
      pct: 70,
      label: "7/10 watched · 3 left",
    });
    assert.equal(formatTvProgress({ total_episode_count: 0 }), null);
  });

  it("filters collection peers excluding self", () => {
    const peers = filterCollectionPeers(
      [
        { title: "Alien", year: 1979, collection_name: "Alien Collection", tmdb_id: 1 },
        { title: "Aliens", year: 1986, collection_name: "Alien Collection", tmdb_id: 2 },
        { title: "Other", year: 2000, collection_name: "Other", tmdb_id: 3 },
      ],
      { title: "Alien", year: 1979, collection_name: "Alien Collection", tmdb_id: 1 },
    );
    assert.equal(peers.length, 1);
    assert.equal(peers[0].title, "Aliens");
  });

  it("builds inline reviews CTA for unrated library titles", () => {
    assert.equal(reviewsCtaForDetail({ in_library: false }), null);
    assert.equal(reviewsCtaForDetail({ in_library: true, user_stars: 4 })?.kind, "rated");
    const rate = reviewsCtaForDetail({ in_library: true });
    assert.equal(rate?.kind, "rate");
    assert.equal(rate?.action, "inline");
    assert.equal(rate?.href, null);
  });

  it("resolves watched state and permission helpers", () => {
    assert.equal(isTitleWatched({ view_count: 2 }), true);
    assert.equal(isTitleWatched({ view_count: 0 }), false);
    assert.equal(watchedCtaLabel({ view_count: 0 }), "Mark as watched");
    assert.equal(watchedCtaLabel({ view_count: 1 }), "Mark as unwatched");
    assert.equal(
      canMarkTitleWatched(
        { in_library: true, rating_key: "1" },
        { role: "member", multiUserEnabled: true },
      ),
      true,
    );
    assert.equal(
      canMarkTitleWatched(
        { in_library: true, rating_key: "1" },
        { role: "guest", multiUserEnabled: true },
      ),
      false,
    );
    assert.equal(
      canMarkTitleWatched(
        { in_library: true, rating_key: "1" },
        { role: "guest", multiUserEnabled: false },
      ),
      true,
    );
  });
});

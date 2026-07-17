import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  filterCollectionPeers,
  formatTvProgress,
  reviewsCtaForDetail,
} from "./titleDetailExtras.js";

describe("titleDetailExtras", () => {
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

  it("builds reviews CTA for unrated library titles", () => {
    assert.equal(reviewsCtaForDetail({ in_library: false }), null);
    assert.equal(reviewsCtaForDetail({ in_library: true, user_stars: 4 })?.kind, "rated");
    assert.equal(reviewsCtaForDetail({ in_library: true })?.href, "/?rate=1");
  });
});

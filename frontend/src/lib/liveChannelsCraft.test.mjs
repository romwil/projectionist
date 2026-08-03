import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  collectionPublishButtonLabel,
  filterLiveCollections,
  findLiveCollection,
} from "./liveChannelsCraft.js";

describe("liveChannelsCraft", () => {
  const collections = [
    { id: "plex:1", title: "Action Pack", label: "Action Pack", source: "plex", media_type: "movie" },
    { id: "pub:2", title: "Kids Hour", label: "Kids Hour", source: "published", media_type: "show" },
    { id: "plex:3", title: "101 Dalmatians", label: "101 Dalmatians", source: "plex", media_type: "movie" },
  ];

  it("filters collections by media scope and search query", () => {
    const tvOnly = filterLiveCollections(collections, { mediaScope: "tv" });
    assert.equal(tvOnly.length, 1);
    assert.equal(tvOnly[0].id, "pub:2");

    const searched = filterLiveCollections(collections, {
      mediaScope: "both",
      filterQuery: "dalmatians",
    });
    assert.equal(searched.length, 1);
    assert.equal(searched[0].title, "101 Dalmatians");
  });

  it("keeps a selected collection visible when filtered out", () => {
    const rows = filterLiveCollections(collections, {
      mediaScope: "tv",
      filterQuery: "action",
      selectedId: "plex:1",
    });
    assert.equal(rows.length, 1);
    assert.equal(rows[0].id, "plex:1");
  });

  it("finds a collection by id", () => {
    assert.equal(findLiveCollection(collections, "pub:2")?.title, "Kids Hour");
    assert.equal(findLiveCollection(collections, ""), null);
  });

  it("builds publish button labels from the selected collection", () => {
    assert.equal(
      collectionPublishButtonLabel({ selected: collections[2] }),
      "Publish “101 Dalmatians”",
    );
    assert.equal(
      collectionPublishButtonLabel({ selected: null, emptyLabel: "Select a collection to publish" }),
      "Select a collection to publish",
    );
    assert.equal(
      collectionPublishButtonLabel({ selected: collections[0], busy: true }),
      "Publishing…",
    );
  });
});

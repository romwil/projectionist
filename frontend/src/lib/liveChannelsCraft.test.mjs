import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  buildCraftFiltersPayload,
  collectionPublishButtonLabel,
  craftDraftFromStation,
  filterGroupsFromCraftFilters,
  filterLiveCollections,
  findLiveCollection,
  withSelectedOption,
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

  it("seeds station Settings draft with the Tunarr channel name and filters", () => {
    const draft = craftDraftFromStation({
      name: "Mystery",
      media_scope: "movies",
      craft_filters: { genres: ["Thriller"], decade: 1970, themes: ["noir"] },
    });
    assert.equal(draft.name, "Mystery");
    assert.equal(draft.media_scope, "movies");
    assert.deepEqual(draft.genres, ["Thriller"]);
    assert.equal(draft.decade, "1970");
    assert.equal(draft.theme, "noir");
    assert.equal(draft.filter_groups.length, 1);
    assert.equal(draft.filter_groups[0].theme, "noir");
  });

  it("loads craft_filters.motifs into the filter group (edit-load)", () => {
    const draft = craftDraftFromStation({
      name: "Drive In",
      craft_filters: { motifs: ["alien"], decade: 1950 },
    });
    assert.equal(draft.filter_groups[0].motif, "alien");
    assert.equal(draft.filter_groups[0].decade, "1950");
  });

  it("loads version-2 OR groups from station_meta", () => {
    const groups = filterGroupsFromCraftFilters({
      version: 2,
      groups: [
        { genres: ["Horror"], decade: 1970 },
        { genres: ["Science Fiction"], themes: ["space"] },
      ],
    });
    assert.equal(groups.length, 2);
    assert.equal(groups[0].genres[0], "Horror");
    assert.equal(groups[1].theme, "space");
  });

  it("serializes OR groups as version-2 craft_filters", () => {
    const payload = buildCraftFiltersPayload({
      filter_groups: [
        { genres: ["Horror"], decade: "1970", theme: "", motif: "", content_rating: "" },
        { genres: ["Science Fiction"], decade: "", theme: "space", motif: "", content_rating: "" },
      ],
    });
    assert.equal(payload.version, 2);
    assert.equal(payload.groups.length, 2);
    assert.equal(payload.groups[0].decade, 1970);
    assert.deepEqual(payload.groups[1].themes, ["space"]);
  });

  it("keeps single-group payloads legacy-flat for migration", () => {
    const payload = buildCraftFiltersPayload({
      filter_groups: [
        { genres: ["Crime"], decade: "", theme: "", motif: "", content_rating: "" },
      ],
    });
    assert.equal(payload.version, undefined);
    assert.deepEqual(payload.genres, ["Crime"]);
  });

  it("injects a saved select value missing from facet options", () => {
    const rows = withSelectedOption(
      [{ value: "Action", label: "Action", count: 3 }],
      "martial arts",
    );
    assert.equal(rows[0].value, "martial arts");
    assert.equal(rows.length, 2);
  });
});

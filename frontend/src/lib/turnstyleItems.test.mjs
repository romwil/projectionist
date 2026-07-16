import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  filterDisplayableCards,
  isDisplayableCard,
  turnstyleItemCount,
} from "./turnstyleItems.js";
import { groupAddableItems } from "./addActions.js";

describe("turnstyleItems", () => {
  it("filters empty placeholder cards", () => {
    const items = [
      { title: "Doctor Who", media_type: "show", tvdb_id: 1 },
      { media_type: "show" },
      { tmdb_id: 99, media_type: "movie" },
    ];
    assert.equal(isDisplayableCard(items[1]), false);
    assert.deepEqual(
      filterDisplayableCards(items).map((item) => item.title || item.tmdb_id),
      ["Doctor Who", 99],
    );
    assert.equal(turnstyleItemCount(items), 2);
  });

  it("aligns expand count with the same set turnstyle renders", () => {
    const payloadItems = [
      { title: "A", media_type: "show", tvdb_id: 1, in_library: false },
      { title: "B", media_type: "show", tmdb_id: 2, in_library: false }, // no tvdb — not Sonarr-addable
      { title: "C", media_type: "show", tvdb_id: 3, in_library: false },
      { media_type: "show" },
    ];
    const displayable = filterDisplayableCards(payloadItems);
    const { sonarr } = groupAddableItems(displayable, { requestPath: "arr" });
    assert.equal(turnstyleItemCount(payloadItems), 3);
    assert.equal(sonarr.length, 2);
  });
});

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";
import {
  BULK_DELETE_CONFIRM_PHRASE,
  canBulkDeleteLibraryItem,
  canOwnerDeleteLibraryTitle,
  exploreSectionToolbarLayoutMatchers,
  formatBulkDeletePreviewTitles,
  formatLibraryDeleteSuccessMessage,
  isBulkDeleteConfirmPhrase,
  libraryDeleteNoticeFromState,
  libraryItemRatingKey,
  LIBRARY_DELETE_NOTICE_KEY,
  partitionBulkDeleteSelection,
} from "./bulkLibraryDelete.js";

const styles = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "..", "styles.css"),
  "utf8",
);

function itemKey(item) {
  return `${item?.media_type || ""}:${item?.tmdb_id || item?.rating_key || item?.title || ""}`;
}

describe("bulkLibraryDelete eligibility", () => {
  it("reads rating_key / plex_rating_key", () => {
    assert.equal(libraryItemRatingKey({ rating_key: "  rk-1  " }), "rk-1");
    assert.equal(libraryItemRatingKey({ plex_rating_key: "plex-9" }), "plex-9");
    assert.equal(libraryItemRatingKey({ tmdb_id: 1 }), "");
  });

  it("allows library items with rating_key and rejects TMDB-only", () => {
    assert.equal(canBulkDeleteLibraryItem({ title: "A", rating_key: "1", in_library: true }), true);
    assert.equal(canBulkDeleteLibraryItem({ title: "B", rating_key: "2" }), true);
    assert.equal(canBulkDeleteLibraryItem({ title: "C", tmdb_id: 99, in_library: false }), false);
    assert.equal(canBulkDeleteLibraryItem({ title: "D", tmdb_id: 99 }), false);
    assert.equal(canBulkDeleteLibraryItem(null), false);
  });

  it("partitions selected items into deletable vs unavailable", () => {
    const items = [
      { media_type: "movie", title: "Keepable", rating_key: "rk-1", tmdb_id: 1 },
      { media_type: "movie", title: "TMDB only", tmdb_id: 2, in_library: false },
      { media_type: "show", title: "Also keep", plex_rating_key: "rk-3", tmdb_id: 3 },
    ];
    const selected = new Set(items.map(itemKey));
    const part = partitionBulkDeleteSelection(items, selected, itemKey);
    assert.equal(part.deletable.length, 2);
    assert.equal(part.unavailable.length, 1);
    assert.deepEqual(part.ratingKeys, ["rk-1", "rk-3"]);
    assert.deepEqual(part.titles, ["Keepable", "Also keep"]);
  });
});

describe("bulkLibraryDelete typed confirm", () => {
  it("requires exact DELETE phrase", () => {
    assert.equal(BULK_DELETE_CONFIRM_PHRASE, "DELETE");
    assert.equal(isBulkDeleteConfirmPhrase("DELETE"), true);
    assert.equal(isBulkDeleteConfirmPhrase(" DELETE "), true);
    assert.equal(isBulkDeleteConfirmPhrase("delete"), false);
    assert.equal(isBulkDeleteConfirmPhrase("YES"), false);
  });

  it("formats preview titles with remainder count", () => {
    const preview = formatBulkDeletePreviewTitles(
      ["One", "Two", "Three", "Four", "Five", "Six"],
      3,
    );
    assert.deepEqual(preview.shown, ["One", "Two", "Three"]);
    assert.equal(preview.remaining, 3);
    assert.equal(preview.total, 6);
  });
});

describe("explore section toolbar layout helper", () => {
  it("documents contained toolbar matchers that styles.css satisfies", () => {
    const matchers = exploreSectionToolbarLayoutMatchers();
    assert.match(styles, matchers.container);
    assert.match(styles, matchers.overflow);
    assert.match(styles, matchers.sortSelect);
    assert.match(styles, matchers.bulkWrap);
  });
});

describe("owner title-detail delete gating", () => {
  const libraryItem = { title: "Dune", rating_key: "rk-1", in_library: true };

  it("allows owner (and single-user) for in-library titles with rating_key", () => {
    assert.equal(
      canOwnerDeleteLibraryTitle(libraryItem, { role: "owner", multiUserEnabled: true }),
      true,
    );
    assert.equal(
      canOwnerDeleteLibraryTitle(libraryItem, { role: "guest", multiUserEnabled: false }),
      true,
    );
  });

  it("hides delete for members, guests, and non-library titles", () => {
    assert.equal(
      canOwnerDeleteLibraryTitle(libraryItem, { role: "member", multiUserEnabled: true }),
      false,
    );
    assert.equal(
      canOwnerDeleteLibraryTitle(libraryItem, { role: "guest", multiUserEnabled: true }),
      false,
    );
    assert.equal(
      canOwnerDeleteLibraryTitle(
        { title: "TMDB only", tmdb_id: 9, in_library: false },
        { role: "owner", multiUserEnabled: true },
      ),
      false,
    );
    assert.equal(
      canOwnerDeleteLibraryTitle(
        { title: "No key", in_library: true },
        { role: "owner", multiUserEnabled: true },
      ),
      false,
    );
  });

  it("formats success notice and reads it from location state", () => {
    assert.equal(
      formatLibraryDeleteSuccessMessage({ deleted: 1, title: "Dune" }),
      'Removed "Dune" from the CuratorX library index.',
    );
    assert.equal(
      formatLibraryDeleteSuccessMessage({ deleted: 0, title: "Dune" }),
      'No matching library record for "Dune".',
    );
    assert.equal(
      libraryDeleteNoticeFromState({ [LIBRARY_DELETE_NOTICE_KEY]: "  ok  " }),
      "ok",
    );
    assert.equal(libraryDeleteNoticeFromState({}), "");
  });

  it("wires title detail surfaces to BulkLibraryDeleteDialog and deleteLibraryItems", () => {
    const libDir = join(dirname(fileURLToPath(import.meta.url)), "..");
    const page = readFileSync(join(libDir, "pages", "TitleDetailPage.jsx"), "utf8");
    const interactions = readFileSync(
      join(libDir, "hooks", "useTitleDetailInteractions.js"),
      "utf8",
    );
    const content = readFileSync(join(libDir, "components", "TitleDetailContent.jsx"), "utf8");
    assert.match(page, /BulkLibraryDeleteDialog/);
    assert.match(page, /canOwnerDeleteLibraryTitle/);
    assert.match(page, /LIBRARY_DELETE_NOTICE_KEY/);
    assert.match(interactions, /deleteLibraryItems/);
    assert.match(content, /data-testid="title-detail-delete-button"/);
  });
});

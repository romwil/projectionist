import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";
import {
  BULK_DELETE_CONFIRM_PHRASE,
  BULK_DELETE_EMPTY_SELECTION_MESSAGE,
  LIBRARY_DELETE_MODE_FULL,
  LIBRARY_DELETE_MODE_INDEX,
  canBulkDeleteLibraryItem,
  canOwnerDeleteLibraryTitle,
  exploreSectionToolbarLayoutMatchers,
  formatBulkDeletePreviewTitles,
  formatBulkLibraryDeleteResultMessage,
  formatRemovalBytes,
  formatRemovalFreedLabel,
  hasRemovalSummary,
  normalizeRemovalSummary,
  removalPathsNote,
  formatLibraryDeleteSuccessMessage,
  isBulkDeleteConfirmPhrase,
  libraryDeleteModeLabel,
  libraryDeleteNoticeFromState,
  libraryItemRatingKey,
  LIBRARY_DELETE_NOTICE_KEY,
  normalizeLibraryDeleteMode,
  partitionBulkDeleteSelection,
} from "./bulkLibraryDelete.js";
import { readAllStyles } from "./readStyles.mjs";

const styles = readAllStyles();

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

  it("freezes selection while delete dialog is open and surfaces empty-confirm errors", () => {
    const libDir = join(dirname(fileURLToPath(import.meta.url)), "..");
    const dialog = readFileSync(
      join(libDir, "components", "BulkLibraryDeleteDialog.jsx"),
      "utf8",
    );
    const dashboard = readFileSync(join(libDir, "pages", "DashboardPage.jsx"), "utf8");
    const browse = readFileSync(join(libDir, "pages", "LibraryBrowsePage.jsx"), "utf8");
    const explore = readFileSync(join(libDir, "pages", "ExploreSectionPage.jsx"), "utf8");
    const watchlist = readFileSync(join(libDir, "pages", "WatchlistPage.jsx"), "utf8");

    assert.match(BULK_DELETE_EMPTY_SELECTION_MESSAGE, /No titles selected/);
    assert.match(dialog, /preview\.total > 0/);
    assert.match(dialog, /No titles selected\. Confirm stays disabled/);
    assert.match(dashboard, /titles=\{selectedTitles\}/);
    assert.match(dashboard, /if \(purgeDialogOpen \|\| actionLoading\) return;/);
    assert.match(dashboard, /disabled=\{purgeDialogOpen \|\| actionLoading\}/);
    assert.match(dashboard, /setPurgeError\(BULK_DELETE_EMPTY_SELECTION_MESSAGE\)/);
    for (const page of [browse, explore, watchlist]) {
      assert.match(page, /if \(deleteOpen \|\| deleting\) return;/);
      assert.match(page, /setDeleteError\(BULK_DELETE_EMPTY_SELECTION_MESSAGE\)/);
      assert.match(page, /titles=\{deletePartition\.titles\}/);
    }
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
      'Removed "Dune" from the Projectionist library index.',
    );
    assert.equal(
      formatLibraryDeleteSuccessMessage({ deleted: 0, title: "Dune" }),
      'No matching library record for "Dune".',
    );
    assert.equal(
      formatLibraryDeleteSuccessMessage({
        deleted: 1,
        title: "Dune",
        mode: LIBRARY_DELETE_MODE_FULL,
      }),
      'Fully removed "Dune" (files via *arr, Plex entry, Projectionist index).',
    );
    assert.equal(
      formatBulkLibraryDeleteResultMessage({
        mode: LIBRARY_DELETE_MODE_FULL,
        deleted: 2,
        errors: [{ error: "Radarr is not configured" }],
      }),
      "Fully removed 2; 1 failed (Radarr is not configured).",
    );
    assert.equal(
      formatBulkLibraryDeleteResultMessage({
        mode: LIBRARY_DELETE_MODE_FULL,
        deleted: 1,
        errors: [],
        totals: { files: 1, folders: 1, bytes_freed: 1024 ** 3 },
      }),
      "Fully removed 1 title from the stack · 1.00 GB freed.",
    );
    assert.equal(formatRemovalBytes(0), "0 B");
    assert.equal(formatRemovalBytes(2048), "2.0 KB");
    assert.equal(
      formatRemovalFreedLabel({
        bytes_freed: 0,
        bytes_source: "unknown",
        files: [],
        folders: ["/tv/Show"],
      }),
      "Size unknown",
    );
    assert.equal(
      formatRemovalFreedLabel({
        bytes_freed: 1024 ** 3,
        bytes_source: "library_estimate",
        files: [],
        folders: ["/tv/Show"],
      }),
      "~1.00 GB (est.)",
    );
    assert.match(
      removalPathsNote({
        files: [],
        folders: ["/tv/Show"],
        note: "",
      }),
      /no episode file list/i,
    );
    assert.equal(
      hasRemovalSummary({
        mode: LIBRARY_DELETE_MODE_FULL,
        results: [{ title: "Dune", files: ["/a.mkv"], folders: ["/a"], bytes_freed: 10 }],
        totals: { files: 1, folders: 1, bytes_freed: 10 },
      }),
      true,
    );
    assert.equal(hasRemovalSummary({ mode: LIBRARY_DELETE_MODE_INDEX, deleted: 1 }), false);
    assert.deepEqual(
      normalizeRemovalSummary({
        mode: LIBRARY_DELETE_MODE_FULL,
        deleted: 1,
        results: [{ title: "Dune", files: ["/a.mkv"], folders: ["/a"], bytes_freed: 10 }],
      }).totals,
      { files: 1, folders: 1, bytes_freed: 10, bytes_source: "unknown" },
    );
    assert.deepEqual(
      normalizeRemovalSummary({
        mode: LIBRARY_DELETE_MODE_FULL,
        deleted: 0,
        results: [
          {
            title: "Ghost",
            files: ["/ghost.mkv"],
            folders: ["/ghost"],
            bytes_freed: 999,
          },
        ],
        totals: { files: 0, folders: 0, bytes_freed: 0 },
      }).totals,
      { files: 0, folders: 0, bytes_freed: 0, bytes_source: "unknown" },
      "API totals of 0 must not fall back to recalculating from results",
    );
    assert.equal(
      normalizeRemovalSummary({
        mode: LIBRARY_DELETE_MODE_FULL,
        deleted: 0,
        results: [{ title: "Ghost", files: [], folders: [], bytes_freed: 0 }],
        totals: { files: 0, folders: 0, bytes_freed: 0 },
      }).deleted,
      0,
    );
    assert.equal(
      formatBulkLibraryDeleteResultMessage({
        mode: LIBRARY_DELETE_MODE_FULL,
        deleted: 1,
        errors: [],
        totals: { files: 0, folders: 0, bytes_freed: 0 },
      }),
      "Fully removed 1 title from the stack.",
    );
    assert.equal(normalizeLibraryDeleteMode("FULL"), LIBRARY_DELETE_MODE_FULL);
    assert.equal(normalizeLibraryDeleteMode("nope"), LIBRARY_DELETE_MODE_INDEX);
    assert.equal(libraryDeleteModeLabel(LIBRARY_DELETE_MODE_FULL), "Fully remove");
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
    const dialog = readFileSync(
      join(libDir, "components", "BulkLibraryDeleteDialog.jsx"),
      "utf8",
    );
    const removalSummary = readFileSync(
      join(libDir, "components", "RemovalSummaryDialog.jsx"),
      "utf8",
    );
    assert.match(page, /BulkLibraryDeleteDialog/);
    assert.match(page, /canOwnerDeleteLibraryTitle/);
    assert.match(page, /LIBRARY_DELETE_NOTICE_KEY/);
    assert.match(interactions, /deleteLibraryItems/);
    assert.match(interactions, /mode/);
    assert.match(content, /data-testid="title-detail-delete-button"/);
    assert.match(dialog, /bulk-library-delete-mode-full/);
    assert.match(dialog, /LIBRARY_DELETE_MODE_FULL/);
    assert.match(
      removalSummary,
      /titleCount = Number\.isFinite\(deleted\) \? deleted : results\.length/,
    );
    assert.doesNotMatch(removalSummary, /titleCount = deleted \|\| results\.length/);
  });

  it("portals delete dialog above title-detail drawer dismiss targets", () => {
    const libDir = join(dirname(fileURLToPath(import.meta.url)), "..");
    const dialog = readFileSync(
      join(libDir, "components", "BulkLibraryDeleteDialog.jsx"),
      "utf8",
    );
    const drawer = readFileSync(join(libDir, "components", "TitleDetailDrawer.jsx"), "utf8");
    const interactions = readFileSync(
      join(libDir, "hooks", "useTitleDetailInteractions.js"),
      "utf8",
    );
    const css = readFileSync(join(libDir, "styles", "10-explore-delight.css"), "utf8");

    assert.match(dialog, /createPortal/);
    assert.match(dialog, /document\.body/);
    assert.match(dialog, /function stopBubble/);
    assert.match(dialog, /onChange=\{\(event\) => selectMode\(LIBRARY_DELETE_MODE_FULL, event\)\}/);
    assert.match(dialog, /onClick=\{stopBubble\}/);
    assert.match(drawer, /interactions\.deleteOpen/);
    assert.match(drawer, /setDeleteOpen\(false\)/);
    // Full-remove success must surface path/size totals from the drawer too —
    // otherwise Storage Intelligence deletes look like a silent no-op.
    assert.match(drawer, /RemovalSummaryDialog/);
    assert.match(drawer, /dismissRemovalSummary/);
    assert.match(interactions, /onDeleteSuccess/);
    assert.match(interactions, /deleteInFlightRef/);

    const backdropRule = css.match(
      /\.bulk-delete-modal-backdrop\s*\{[^}]*z-index:\s*(\d+)/s,
    );
    const scrimRule = css.match(/\.title-detail-drawer-scrim\s*\{[^}]*z-index:\s*(\d+)/s);
    const panelRule = css.match(/\.title-detail-drawer-panel\s*\{[^}]*z-index:\s*(\d+)/s);
    assert.ok(backdropRule, "expected bulk-delete-modal-backdrop z-index");
    assert.ok(scrimRule, "expected title-detail-drawer-scrim z-index");
    assert.ok(panelRule, "expected title-detail-drawer-panel z-index");
    const backdropZ = Number(backdropRule[1]);
    const scrimZ = Number(scrimRule[1]);
    const panelZ = Number(panelRule[1]);
    assert.ok(
      backdropZ > scrimZ && backdropZ > panelZ,
      `delete dialog z-index (${backdropZ}) must exceed drawer scrim (${scrimZ}) and panel (${panelZ})`,
    );
  });
});

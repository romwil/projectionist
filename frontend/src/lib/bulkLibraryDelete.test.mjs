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
  canConfirmLibraryRemoval,
  isBulkDeleteConfirmPhrase,
  libraryDeleteModeLabel,
  libraryRemovalNeedsTypedDelete,
  libraryDeleteNoticeFromState,
  libraryBrowseItemKey,
  libraryItemRatingKey,
  LIBRARY_DELETE_NOTICE_KEY,
  normalizeLibraryDeleteMode,
  partitionBulkDeleteSelection,
} from "./bulkLibraryDelete.ts";
import { readAllStyles } from "./readStyles.mjs";

const styles = readAllStyles();

describe("libraryBrowseItemKey", () => {
  it("prefers rating_key over shared tmdb_id", () => {
    const a = { media_type: "movie", tmdb_id: 999, rating_key: "plex-a", title: "72 Hours" };
    const b = { media_type: "movie", tmdb_id: 999, rating_key: "plex-b", title: "72 Hours" };
    const keyA = libraryBrowseItemKey(a);
    const keyB = libraryBrowseItemKey(b);
    assert.notEqual(keyA, keyB);
    assert.match(keyA, /plex-a$/);
    assert.match(keyB, /plex-b$/);
  });

  it("falls back to tmdb_id for external-only cards", () => {
    assert.equal(
      libraryBrowseItemKey({ media_type: "movie", tmdb_id: 42, title: "External" }),
      "movie:tmdb:42",
    );
  });
});

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
    const selected = new Set(items.map(libraryBrowseItemKey));
    const part = partitionBulkDeleteSelection(items, selected, libraryBrowseItemKey);
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
    const languageLanding = readFileSync(join(libDir, "pages", "LanguageLandingPage.jsx"), "utf8");
    const watchlist = readFileSync(join(libDir, "pages", "WatchlistPage.jsx"), "utf8");

    assert.match(BULK_DELETE_EMPTY_SELECTION_MESSAGE, /No titles selected/);
    assert.match(dialog, /preview\.total > 0/);
    assert.match(dialog, /No titles selected\. Confirm stays disabled/);
    assert.match(dashboard, /titles=\{selectedTitles\}/);
    assert.match(dashboard, /if \(purgeDialogOpen \|\| actionLoading\) return;/);
    assert.match(dashboard, /disabled=\{purgeDialogOpen \|\| actionLoading\}/);
    assert.match(dashboard, /setPurgeError\(BULK_DELETE_EMPTY_SELECTION_MESSAGE\)/);
    for (const page of [browse, explore, watchlist, languageLanding]) {
      assert.match(page, /if \(deleteOpen \|\| deleting\) return;/);
      assert.match(page, /setDeleteError\(BULK_DELETE_EMPTY_SELECTION_MESSAGE\)/);
      assert.match(page, /titles=\{deletePartition\.titles\}/);
    }
  });
});

describe("typed DELETE preference", () => {
  it("requires DELETE until the owner opts out", () => {
    assert.equal(libraryRemovalNeedsTypedDelete(undefined), true);
    assert.equal(libraryRemovalNeedsTypedDelete(true), true);
    assert.equal(libraryRemovalNeedsTypedDelete(false), false);
    assert.equal(
      canConfirmLibraryRemoval({
        needsTypedDelete: true,
        phrase: "",
        hasTarget: true,
        loading: false,
      }),
      false,
    );
    assert.equal(
      canConfirmLibraryRemoval({
        needsTypedDelete: true,
        phrase: "delete",
        hasTarget: true,
      }),
      false,
    );
    assert.equal(
      canConfirmLibraryRemoval({
        needsTypedDelete: true,
        phrase: "DELETE",
        hasTarget: true,
      }),
      true,
    );
  });

  it("lets removal proceed without the typed word when the setting is off", () => {
    assert.equal(
      canConfirmLibraryRemoval({
        needsTypedDelete: libraryRemovalNeedsTypedDelete(false),
        phrase: "",
        hasTarget: true,
        loading: false,
      }),
      true,
    );
    assert.equal(
      canConfirmLibraryRemoval({
        needsTypedDelete: false,
        phrase: "",
        hasTarget: false,
      }),
      false,
    );
  });

  it("keeps scope choice and hides the DELETE field when confirmation is off", () => {
    const libDir = join(dirname(fileURLToPath(import.meta.url)), "..");
    const dialog = readFileSync(join(libDir, "components", "BulkLibraryDeleteDialog.jsx"), "utf8");
    const phrase = readFileSync(join(libDir, "components", "DeleteConfirmPhrase.jsx"), "utf8");
    const scoped = readFileSync(join(libDir, "components", "ScopedTvRemoveDialog.jsx"), "utf8");
    const libraries = readFileSync(join(libDir, "pages", "admin", "LibrariesSection.jsx"), "utf8");
    const styles = readFileSync(join(libDir, "styles", "10-explore-delight.css"), "utf8");

    assert.match(dialog, /bulk-library-delete-modes/);
    assert.match(dialog, /libraryRemovalNeedsTypedDelete/);
    assert.match(dialog, /canConfirmLibraryRemoval/);
    assert.match(dialog, /DeleteConfirmPhrase/);
    assert.match(phrase, /Don&apos;t ask again/);
    assert.match(phrase, /if \(!libraryRemovalNeedsTypedDelete\(askDeleteConfirmation\)\) return null/);
    assert.match(phrase, /saveAskDeleteConfirmation\(false\)/);
    assert.match(scoped, /DeleteConfirmPhrase/);
    assert.match(scoped, /This deletes media files through Sonarr/);
    assert.match(libraries, /Ask me to type DELETE before removing titles/);
    assert.match(libraries, /ask-delete-confirmation-toggle/);
    assert.match(styles, /\.bulk-delete-dont-ask\s*\{[^}]*min-height:\s*44px/s);
    assert.match(styles, /\[data-testid="ask-delete-confirmation-toggle"\] \.settings-switch\s*\{[^}]*min-height:\s*44px/s);
    assert.match(styles, /\.bulk-delete-dont-ask\s*\{[^}]*color:\s*var\(--text\)/s);
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
        bytes_freed: 4096,
        bytes_source: "disk",
        files: ["/tv/Show/S01E01.mkv"],
        folders: ["/tv/Show"],
        note: '"The Show" is not in Sonarr',
      }),
      "4.0 KB",
    );
    assert.equal(
      formatRemovalFreedLabel({
        bytes_freed: 0,
        bytes_source: "unknown",
        files: 0,
        folders: 0,
        note: '"The Show" is not in Sonarr. File path was unknown.',
      }),
      "0 B",
    );
    const absent = normalizeRemovalSummary({
      mode: LIBRARY_DELETE_MODE_FULL,
      deleted: 1,
      results: [
        {
          title: "The Show",
          ok: true,
          files: ["/tv/Show/S01E01.mkv"],
          folders: ["/tv/Show"],
          bytes_freed: 4096,
          bytes_source: "disk",
          note: '"The Show" is not in Sonarr',
        },
      ],
      totals: { files: 1, folders: 1, bytes_freed: 4096 },
      errors: [],
    });
    assert.equal(absent.totals.bytes_freed, 4096);
    assert.equal(absent.totals.files, 1);
    assert.equal(absent.results[0].note, '"The Show" is not in Sonarr');
    assert.equal(absent.errors.length, 0);
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
      join(libDir, "hooks", "useTitleDetailInteractions.ts"),
      "utf8",
    );
    const content = readFileSync(join(libDir, "components", "TitleDetailContent.jsx"), "utf8");
    const ctaBar = readFileSync(join(libDir, "components", "TitleCtaBar.jsx"), "utf8");
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
    assert.match(content, /canDeleteLibrary=\{canDeleteLibrary\}/);
    assert.match(ctaBar, /data-testid="title-detail-delete-button"/);
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
      join(libDir, "hooks", "useTitleDetailInteractions.ts"),
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
    const panelRule = css.match(
      /\.title-detail-drawer-panel(?:\s*,\s*[^{]+)?\s*\{[^}]*z-index:\s*(\d+)/s,
    );
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

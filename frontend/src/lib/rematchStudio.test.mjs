import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  GOOD_NEWS_NOT_DOWNLOAD,
  INVESTIGATORS_NOTE,
  collectRepairItems,
  folderColumnCopy,
  humanizeMiss,
  identityKindLabel,
  looksLikeJsonDump,
  plexColumnCopy,
  radarrColumnCopy,
  repairActionsFor,
} from "./rematchStudio.js";

const here = dirname(fileURLToPath(import.meta.url));
const libraries = readFileSync(join(here, "../pages/admin/LibrariesSection.jsx"), "utf8");
const rematch = readFileSync(join(here, "../pages/admin/RematchStudio.jsx"), "utf8");
const repair = readFileSync(join(here, "../pages/admin/RepairMiss.jsx"), "utf8");

describe("rematch studio copy", () => {
  it("labels Presence/Savages vs same-title conflicts", () => {
    assert.equal(identityKindLabel("path_conflict", false), "Path conflict");
    assert.equal(identityKindLabel("path_conflict", true), "Same title, path conflict");
    assert.equal(identityKindLabel("title_collision", true), "Same title, different identity");
    assert.equal(identityKindLabel("needs_plex_id"), "Needs a Plex rematch");
  });

  it("shows three identity columns", () => {
    const row = {
      title: "Presence",
      folder: "/movies/Presence (2025)",
      plex: { title: "Presence", tmdb_id: 1388150 },
      radarr: { title: "Savages", tmdb_id: 111, folder_path: "/movies/Presence (2025)" },
    };
    assert.match(plexColumnCopy(row), /tmdb 1388150/);
    assert.match(radarrColumnCopy(row), /Savages/);
    assert.match(radarrColumnCopy(row), /tmdb 111/);
    assert.equal(folderColumnCopy(row), "/movies/Presence (2025)");
  });

  it("never surfaces a JSON dump for a miss", () => {
    const raw =
      'HTTP 400 from http://radarr: [{"errorCode":"MoviePathValidator","formattedMessagePlaceholderValues":{"path":"/movies/Presence (2025)"}}]';
    assert.equal(looksLikeJsonDump(raw), true);
    assert.equal(humanizeMiss(raw).includes("formattedMessagePlaceholderValues"), false);
    assert.equal(humanizeMiss(raw).includes('"errorCode"'), false);
  });

  it("offers rematch skip retry Investigate by kind", () => {
    assert.deepEqual(repairActionsFor("path_conflict", "movie"), ["rematch", "skip", "retry"]);
    assert.deepEqual(repairActionsFor("failed", "show"), ["retry", "investigate", "skip"]);
    assert.deepEqual(repairActionsFor("needs_plex_id", "movie"), ["rematch", "skip"]);
  });

  it("collects failed register and Sonarr search rows", () => {
    const items = collectRepairItems(
      {
        items: [
          {
            id: 4,
            title: "Presence (2025)",
            status: "failed",
            outcome: "path_conflict",
            error: '{"errorCode":"MoviePathValidator"}',
          },
        ],
      },
      { execution: { failed: 1, last_error: '{"errorCode":"x"}' } },
    );
    assert.equal(items.length, 2);
    assert.equal(items[0].actions.includes("rematch"), true);
    assert.equal(items[1].actions.includes("investigate"), true);
    assert.equal(items[0].message.includes("errorCode"), false);
  });

  it("wires Rematch studio and Repair the miss on Libraries", () => {
    assert.match(libraries, /RematchStudio/);
    assert.match(libraries, /RepairMiss/);
    assert.match(libraries, /data-testid="rematch-studio-card"|RematchStudio/);
    assert.match(rematch, /data-testid="rematch-studio-card"/);
    assert.match(rematch, /Scan identities/);
    assert.match(repair, /data-testid="repair-miss-card"/);
    assert.match(repair, /Rematch/);
    assert.match(repair, /Investigate/);
    assert.match(INVESTIGATORS_NOTE, /FileBot/);
    assert.match(INVESTIGATORS_NOTE, /Plex Match/);
    assert.match(GOOD_NEWS_NOT_DOWNLOAD, /download complete/);
  });
});

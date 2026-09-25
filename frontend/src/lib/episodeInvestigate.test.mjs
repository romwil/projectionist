import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  FFMPEG_MISSING,
  SCENE_NAMES_NOT_EVIDENCE,
  STILLS_LEAVE_LAN,
  applyButtonClass,
  confidenceLabel,
  defaultRowSelected,
  reviewEvidenceSummary,
  selectedFileIds,
  selectionMap,
  UNREADABLE_MEDIA,
} from "./episodeInvestigate.js";

const here = dirname(fileURLToPath(import.meta.url));
const libraries = readFileSync(join(here, "../pages/admin/LibrariesSection.jsx"), "utf8");

const emptyEvidenceRows = [
  { id: "a", confidence: "uncertain", stills: [], identify: { found: false }, reasons: ["not enough independent evidence"] },
  { id: "b", confidence: "uncertain", stills: [], identify: { found: false }, reasons: ["not enough independent evidence"] },
];

describe("episode investigate selection", () => {
  it("selects Certain and Likely, leaves Uncertain off", () => {
    const rows = [
      { id: "a", confidence: "certain", same_show: true, selected_default: true },
      { id: "b", confidence: "likely", same_show: true, selected_default: true },
      { id: "c", confidence: "uncertain", same_show: true, selected_default: false },
      { id: "d", confidence: "certain", same_show: false, selected_default: false },
    ];
    const selected = selectionMap(rows);
    assert.equal(selected.a, true);
    assert.equal(selected.b, true);
    assert.equal(selected.c, false);
    assert.equal(selected.d, false);
    assert.deepEqual(selectedFileIds(rows, selected), ["a", "b"]);
    assert.equal(defaultRowSelected(rows[2]), false);
    assert.equal(confidenceLabel("likely"), "Likely");
  });

  it("wires Investigate on Libraries, not ConfigPage, with LAN stills copy", () => {
    assert.match(libraries, /data-testid="episode-investigate-card"/);
    assert.match(libraries, /InvestigatePanel/);
    assert.match(libraries, /STILLS_LEAVE_LAN/);
    assert.match(libraries, /SCENE_NAMES_NOT_EVIDENCE/);
    assert.match(libraries, /\/admin\/investigate\/start/);
    assert.equal(STILLS_LEAVE_LAN.includes("leave the LAN"), true);
    assert.equal(SCENE_NAMES_NOT_EVIDENCE.includes("not evidence"), true);
  });

  it("uses a dense review table with sticky Apply, not stacked cards", () => {
    assert.match(libraries, /investigate-review-table/);
    assert.match(libraries, /investigate-review-actions/);
    assert.match(libraries, /InvestigateReviewRow/);
    assert.match(libraries, /applyButtonClass/);
    assert.doesNotMatch(libraries, /Filename claim<\/strong> — not evidence/);
    assert.doesNotMatch(libraries, /gridTemplateColumns: "1fr 1fr"/);
  });

  it("does not tell the owner to install a host ffmpeg binary", () => {
    assert.match(libraries, /FFMPEG_MISSING/);
    assert.match(libraries, /investigate-evidence-summary/);
    assert.doesNotMatch(libraries, /host ffmpeg binary/);
    assert.doesNotMatch(libraries, /Install a host binary/);
    assert.match(FFMPEG_MISSING, /container/);
    assert.match(FFMPEG_MISSING, /FFMPEG_PATH/);
    assert.doesNotMatch(FFMPEG_MISSING, /Install a host/);
    assert.doesNotMatch(FFMPEG_MISSING, /Unraid host/);
  });

  it("gold Apply only when at least one same-show row is selected", () => {
    assert.equal(applyButtonClass(0), "ghost");
    assert.equal(applyButtonClass(2), "primary");
  });

  it("summarizes empty evidence as a finished run, not work in flight", () => {
    const missing = reviewEvidenceSummary(emptyEvidenceRows, {
      ffmpegReady: false,
      visionOn: true,
      identifyConfigured: true,
    });
    assert.match(missing, /ffmpeg is missing from this container/);
    assert.match(missing, /Fusion is done/);
    assert.match(missing, /not still running/);
    assert.match(missing, /FFMPEG_PATH/);
    assert.doesNotMatch(missing, /host binary/);

    const allUncertain = reviewEvidenceSummary(emptyEvidenceRows, {
      ffmpegReady: true,
      visionOn: true,
      identifyConfigured: true,
    });
    assert.match(allUncertain, /All 2 rows are Uncertain/);
    assert.match(allUncertain, /No stills were extracted/);
    assert.match(allUncertain, /Identify did not return a match/);
    assert.match(allUncertain, /Fusion is done/);

    const mixed = reviewEvidenceSummary(
      [
        { id: "a", confidence: "certain", stills: ["/s.jpg"], identify: { found: true } },
        { id: "b", confidence: "uncertain", stills: [], identify: { found: false } },
      ],
      { ffmpegReady: true, visionOn: true, identifyConfigured: true },
    );
    assert.equal(mixed, "");

    const unreadable = reviewEvidenceSummary(
      emptyEvidenceRows.map((row) => ({ ...row, stills_error: "unreadable_path" })),
      { ffmpegReady: true, visionOn: true, identifyConfigured: false },
    );
    assert.match(unreadable, /No stills were extracted/);
    assert.match(unreadable, /Bind-mount the TV library/);
    assert.match(unreadable, new RegExp(UNREADABLE_MEDIA.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
    assert.doesNotMatch(libraries, /row\.same_show === false \? " · other show/);
  });
});

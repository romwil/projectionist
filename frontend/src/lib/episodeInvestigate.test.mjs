import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  ALL_UNCERTAIN_NEXT_STEPS,
  FFMPEG_MISSING,
  IDENTIFY_CLIP_SECONDS,
  IDENTIFY_LEAVES_LAN,
  IDENTIFY_TEST_NO_RENAME,
  OPEN_STILLS_LABEL,
  REVIEW_GUIDANCE_APPLY,
  REVIEW_GUIDANCE_CERTAIN,
  REVIEW_GUIDANCE_INTRO,
  REVIEW_GUIDANCE_LIKELY,
  REVIEW_GUIDANCE_UNCERTAIN,
  RUNTIME_ONLY_LIKELY_BANNER,
  SCENE_NAMES_NOT_EVIDENCE,
  STILLS_LEAVE_LAN,
  applyButtonClass,
  confidenceLabel,
  defaultRowSelected,
  filterInvestigateShows,
  formatInvestigateShowLabel,
  hasRuntimeOnlyLikelyRows,
  identifyTestHonestyLine,
  identifyTestRenamed,
  investigateSeasonOptions,
  isAllUncertainBatch,
  isRuntimeOnlyLikely,
  reviewEvidenceSummary,
  selectedFileIds,
  selectionMap,
  UNREADABLE_MEDIA,
} from "./episodeInvestigate.js";

const here = dirname(fileURLToPath(import.meta.url));
const libraries = readFileSync(join(here, "../pages/admin/LibrariesSection.jsx"), "utf8");
const showCombobox = readFileSync(join(here, "../components/InvestigateShowCombobox.jsx"), "utf8");

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

  it("does not auto-select runtime-only Likely and surfaces review guidance", () => {
    const runtimeOnly = {
      id: "r",
      confidence: "likely",
      same_show: true,
      selected_default: true,
      signals: { runtime_key: [17, 5], oshash_key: null, vision_key: null, runtime_only: true },
      reasons: ["runtime matches S17E05"],
      stills: ["/s.jpg"],
      tmdb_stills: ["/t.jpg"],
    };
    const oshashLikely = {
      id: "o",
      confidence: "likely",
      same_show: true,
      selected_default: true,
      signals: { runtime_key: null, oshash_key: [1, 7], vision_key: null, runtime_only: false },
      reasons: ["OpenSubtitles hash points at S01E07"],
    };
    assert.equal(isRuntimeOnlyLikely(runtimeOnly), true);
    assert.equal(defaultRowSelected(runtimeOnly), false);
    assert.equal(defaultRowSelected(oshashLikely), true);
    assert.equal(hasRuntimeOnlyLikelyRows([runtimeOnly, oshashLikely]), true);
    assert.equal(isAllUncertainBatch([{ confidence: "uncertain" }, { confidence: "uncertain" }]), true);
    assert.equal(isAllUncertainBatch([runtimeOnly]), false);

    assert.match(libraries, /investigate-review-guidance/);
    assert.match(libraries, /investigate-runtime-only-banner/);
    assert.match(libraries, /REVIEW_GUIDANCE_INTRO/);
    assert.match(libraries, /RUNTIME_ONLY_LIKELY_BANNER/);
    assert.match(libraries, /OPEN_STILLS_LABEL/);
    assert.match(libraries, /compare TMDB/);
    assert.match(REVIEW_GUIDANCE_INTRO, /independent evidence/i);
    assert.match(REVIEW_GUIDANCE_CERTAIN, /Certain/);
    assert.match(REVIEW_GUIDANCE_LIKELY, /runtime-only/);
    assert.match(REVIEW_GUIDANCE_UNCERTAIN, /Open stills/);
    assert.match(REVIEW_GUIDANCE_APPLY, /same show/);
    assert.match(RUNTIME_ONLY_LIKELY_BANNER, /Runtime-only Likely/);
    assert.match(RUNTIME_ONLY_LIKELY_BANNER, /docu series/);
    assert.equal(OPEN_STILLS_LABEL, "Open stills");
  });

  it("wires Investigate on Libraries, not ConfigPage, with LAN stills copy", () => {
    assert.match(libraries, /data-testid="episode-investigate-card"/);
    assert.match(libraries, /InvestigatePanel/);
    assert.match(libraries, /InvestigateShowCombobox/);
    assert.match(libraries, /STILLS_LEAVE_LAN/);
    assert.match(libraries, /IDENTIFY_LEAVES_LAN/);
    assert.match(libraries, /SCENE_NAMES_NOT_EVIDENCE/);
    assert.match(libraries, /\/admin\/investigate\/start/);
    assert.equal(STILLS_LEAVE_LAN.includes("leave the LAN"), true);
    assert.equal(SCENE_NAMES_NOT_EVIDENCE.includes("not evidence"), true);
  });

  it("uses a searchable show combobox, not a scroll-only native select", () => {
    assert.match(showCombobox, /role="combobox"/);
    assert.match(showCombobox, /data-testid="investigate-show"/);
    assert.match(showCombobox, /data-testid="investigate-show-list"/);
    assert.match(showCombobox, /filterInvestigateShows/);
    assert.match(showCombobox, /moveTypeaheadIndex/);
    assert.doesNotMatch(libraries, /<select[\s\S]*data-testid="investigate-show"/);
    assert.match(libraries, /data-testid="investigate-season"/);
    assert.match(libraries, /\/admin\/investigate\/seasons/);
    assert.match(libraries, /investigateSeasonOptions/);

    const shows = [
      { id: 1, title: "Expedition Unknown", year: 2015 },
      { id: 2, title: "The Expanse", year: 2015 },
      { id: 3, title: "Unknown", year: 2011 },
      { id: 4, title: "Better Call Saul", year: 2015 },
    ];
    assert.equal(formatInvestigateShowLabel(shows[0]), "Expedition Unknown (2015)");
    const hits = filterInvestigateShows(shows, "exp");
    assert.deepEqual(
      hits.map((item) => item.id),
      [1, 2],
    );
    assert.equal(filterInvestigateShows(shows, "zzzz").length, 0);
    assert.equal(filterInvestigateShows(shows, "", { limit: 2 }).length, 2);
    assert.deepEqual(investigateSeasonOptions([0, 17, 1], 18), [0, 1, 17]);
    assert.deepEqual(investigateSeasonOptions([], 18), []);
    assert.deepEqual(investigateSeasonOptions(null, 3), [1, 2, 3]);
    assert.deepEqual(investigateSeasonOptions(null, 0), []);
  });

  it("says Identify leaves the LAN and that a test miss does not rename", () => {
    assert.equal(IDENTIFY_CLIP_SECONDS, 12);
    assert.match(IDENTIFY_LEAVES_LAN, new RegExp(`${IDENTIFY_CLIP_SECONDS}-second`));
    assert.match(IDENTIFY_LEAVES_LAN, /leaves the LAN/);
    assert.match(IDENTIFY_LEAVES_LAN, /does not rename/);
    assert.equal(identifyTestRenamed({ renamed: true }), false);
    assert.equal(identifyTestRenamed({ renamed: false, found: true }), false);
    assert.equal(identifyTestHonestyLine({ renamed: true }), IDENTIFY_TEST_NO_RENAME);
    assert.match(libraries, /IdentifySettingsPanel/);
    assert.match(libraries, /Save Identify settings/);
    assert.match(libraries, /Test Identify/);
    assert.match(libraries, /IDENTIFY_TEST_NO_RENAME/);
    assert.match(libraries, /\/admin\/investigate\/identify\/settings/);
    assert.match(libraries, /\/admin\/investigate\/identify\/test/);
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
    assert.match(allUncertain, new RegExp(ALL_UNCERTAIN_NEXT_STEPS.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
    assert.match(allUncertain, /OpenSubtitles/);
    assert.match(allUncertain, /do not Apply blindly/);

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
    assert.match(unreadable, /mapping configured TV\/Sonarr roots/);
    assert.match(unreadable, new RegExp(UNREADABLE_MEDIA.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
    assert.doesNotMatch(libraries, /row\.same_show === false \? " · other show/);
  });
});

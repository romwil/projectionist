import assert from "node:assert/strict";
import test from "node:test";

import { gpuDecisionLine, playabilityNotice, sourceBreakdownLine } from "./playabilityNotice.ts";

const STOPPED = "The walk stopped early. Refresh to finish the library.";

test("a stopped walk still shows its message when profile rows are present", () => {
  const notice = playabilityNotice({
    complete: false,
    running: false,
    message: STOPPED,
    profiles: [{ profile: "safari", title_count: 2 }],
  });
  assert.equal(notice, STOPPED);
});

test("an empty library keeps its own message", () => {
  assert.equal(
    playabilityNotice({
      complete: true,
      running: false,
      message: "The library has no titles to check yet.",
      profiles: [],
    }),
    "The library has no titles to check yet.",
  );
  assert.equal(
    playabilityNotice({ complete: false, running: false, profiles: [] }),
    "No playability report yet. Refresh to walk the library.",
  );
});

test("a finished report with rows does not repeat the summary as an empty state", () => {
  assert.equal(
    playabilityNotice({
      complete: true,
      running: false,
      message: "Planned 4 titles from Plex metadata. Confirmed 4 with ffprobe.",
      profiles: [{ profile: "safari", title_count: 4 }],
    }),
    "",
  );
});

test("the source-transcode breakdown names codec, level, bit depth, size, and HDR", () => {
  assert.equal(sourceBreakdownLine(null), "");
  assert.equal(sourceBreakdownLine({ video_transcode: 0 }), "");
  assert.equal(
    sourceBreakdownLine({
      video_transcode: 9506,
      codec: 8000,
      level: 1000,
      bit_depth: 506,
      resolution: 3000,
      hdr: 1200,
    }),
    "Video transcode 9506: codec 8000, level 1000, bit depth 506. Above 1080p 3000. HDR 1200.",
  );
});

test("the video-transcode bucket names codecs and does not show an unconfirmed zero", () => {
  assert.equal(
    sourceBreakdownLine({
      video_transcode: 2084,
      codec: 2084,
      codecs: { mpeg4: 884, av1: 851, mpeg2video: 218 },
      level: null,
      bit_depth: 0,
      resolution: 7,
      hdr: null,
    }),
    "Video transcode 2084: MPEG-4 884, AV1 851, MPEG-2 218. codec 2084, level not confirmed yet, bit depth 0. Above 1080p 7. HDR not confirmed yet.",
  );
});

test("the GPU line is the Safari and Apple TV video-transcode counts", () => {
  assert.equal(gpuDecisionLine(null), "");
  assert.equal(
    gpuDecisionLine({ safari: 40, apple_tv: 12 }),
    "Safari would need a video transcode for 40 titles. Apple TV would need a video transcode for 12 titles.",
  );
  assert.equal(
    gpuDecisionLine({ safari: 0, apple_tv: null }),
    "Safari would need a video transcode for 0 titles.",
  );
});

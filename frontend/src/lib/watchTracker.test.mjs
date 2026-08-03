import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";

import {
  completionConfidenceLabel,
  completionExplanation,
  normalizeWatchSummary,
  trackedCompletionCardLabel,
} from "./watchTracker.js";

describe("watch tracker presentation", () => {
  it("keeps no-coverage summaries on the labeled Plex fallback", () => {
    const summary = normalizeWatchSummary({
      tracker_coverage: "none",
      plex_played_event_count: 3,
    });

    assert.equal(summary.hasCoverage, false);
    assert.equal(summary.fallbackLabel, "Plex marked played 3 times");
    assert.equal(trackedCompletionCardLabel(summary), "");
  });

  it("uses honest tracked-completion and confidence vocabulary", () => {
    const summary = normalizeWatchSummary({
      tracker_coverage: "partial",
      tracked_completions: 2,
      logical_viewings: 2,
      sittings_observed: 4,
      completion_confidence: { certain: 1, likely: 0, plex_event_only: 1 },
      completion_timeline: [
        {
          completed_at_ms: 1_704_067_800_000,
          confidence: "plex_event_only",
          basis: "unique_played_event",
        },
      ],
    });

    assert.equal(trackedCompletionCardLabel(summary), "2 tracked completions");
    assert.equal(completionConfidenceLabel("certain"), "Certain");
    assert.equal(completionConfidenceLabel("plex_event_only"), "Plex played event");
    assert.match(completionExplanation(summary.timeline[0]), /does not prove uninterrupted/);
  });

  it("wires title, show, episode, and card surfaces", () => {
    const src = dirname(fileURLToPath(import.meta.url));
    const components = join(src, "..", "components");
    const detail = readFileSync(join(components, "TitleDetailContent.jsx"), "utf8");
    const seasons = readFileSync(join(components, "ShowSeasonsPanel.jsx"), "utf8");
    const card = readFileSync(join(components, "TitleCard.jsx"), "utf8");
    const timeline = readFileSync(join(components, "WatchHistoryTimeline.jsx"), "utf8");

    assert.match(detail, /WatchHistoryTimeline/);
    assert.match(seasons, /getShowWatchSummary/);
    assert.match(seasons, /episode_completions/);
    assert.match(card, /trackedCompletionCardLabel/);
    assert.match(timeline, /Why this count\?/);
    assert.match(timeline, /Your watch history/);
  });
});

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import LiveGuide from "../components/live/LiveGuide.tsx";
import {
  formatGuideProgramTimeRange,
  guideProgramAccessibleName,
} from "./liveChannels.js";

function localEpoch(year, month, day, hour, minute) {
  return new Date(year, month - 1, day, hour, minute, 0, 0).getTime() / 1000;
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

describe("Live guide cells show a from–to time", () => {
  const heat = {
    title: "Heat",
    start: localEpoch(2026, 11, 1, 20, 0),
    stop: localEpoch(2026, 11, 1, 21, 30),
    rating: "R",
  };
  const night = {
    title: "Night Shift",
    start: localEpoch(2026, 11, 1, 23, 30),
    stop: localEpoch(2026, 11, 2, 1, 0),
  };
  const heatRange = formatGuideProgramTimeRange(heat);
  const nightRange = formatGuideProgramTimeRange(night);

  const guide = {
    ready: true,
    windowStart: heat.start - 3600,
    windowEnd: night.stop + 3600,
    channels: [
      { id: "c1", name: "Drama", number: 4, programs: [heat, night] },
      { id: "c2", name: "Open", number: 5, programs: [] },
    ],
  };

  function render(props = {}) {
    return renderToStaticMarkup(
      createElement(LiveGuide, {
        guide,
        selectedProgramKey: `c1:${heat.start}:Heat`,
        ...props,
      }),
    );
  }

  it("prints the schedule range on the selected show and on a later show", () => {
    const html = render();
    assert.ok(heatRange);
    assert.ok(nightRange);
    assert.doesNotMatch(heatRange, /2026-|T\d{2}:/);
    assert.equal(html.match(/data-testid="live-guide-cell-time"/g)?.length, 2);

    const selected = html.match(
      /<button[^>]*class="live-guide-cell is-focused is-selected"[^>]*>[\s\S]*?<\/button>/,
    );
    assert.ok(selected, "selected cell missing");
    assert.match(selected[0], />Heat</);
    assert.match(selected[0], new RegExp(`>${escapeRegExp(heatRange)}<`));
    assert.match(
      selected[0],
      new RegExp(`aria-label="${escapeRegExp(guideProgramAccessibleName("Heat", heatRange, "R"))}"`),
    );

    assert.match(html, />Night Shift</);
    assert.match(html, new RegExp(`>${escapeRegExp(nightRange)}<`));
    assert.match(
      html,
      new RegExp(`aria-label="${escapeRegExp(guideProgramAccessibleName("Night Shift", nightRange))}"`),
    );
  });

  it("leaves an empty station empty", () => {
    const html = render();
    const rows = html.split('data-testid="live-guide-row"').slice(1);
    assert.equal(rows.length, 2);
    assert.match(rows[0], /Heat/);
    assert.doesNotMatch(rows[1], /live-guide-cell/);
    assert.doesNotMatch(rows[1], /live-guide-cell-time/);
  });

  it("does not invent programmes when the guide is not ready", () => {
    const html = renderToStaticMarkup(
      createElement(LiveGuide, { guide: { ready: false, reason: "youth", channels: [] } }),
    );
    assert.match(html, /data-testid="live-guide-empty"/);
    assert.doesNotMatch(html, /live-guide-cell/);
    assert.doesNotMatch(html, /live-guide-cell-time/);
  });
});

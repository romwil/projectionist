import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import LiveGuide from "../components/live/LiveGuide.tsx";
import { guideChannelLabel } from "./liveChannels.js";

const src = join(dirname(fileURLToPath(import.meta.url)), "..");

const guide = {
  ready: true,
  windowStart: 1_800_000_000,
  windowEnd: 1_800_000_000 + 4 * 3600,
  channels: [
    {
      id: "c1",
      name: "Drama",
      number: 4,
      programs: [
        { title: "Heat", start: 1_800_000_000, stop: 1_800_005_400, rating: "R" },
        { title: "Collateral", start: 1_800_005_400, stop: 1_800_012_600 },
      ],
    },
    {
      id: "c2",
      name: "Youth Safe",
      number: 12,
      programs: [{ title: "Paddington", start: 1_800_000_000, stop: 1_800_006_000, rating: "PG" }],
    },
    { id: "c3", name: "Unnumbered", programs: [{ title: "Flex", start: 1_800_000_000, stop: 1_800_001_800, isFlex: true }] },
  ],
};

function render() {
  return renderToStaticMarkup(createElement(LiveGuide, { guide }));
}

/** Every element subtree rooted at an aria-hidden="true" node. */
function ariaHiddenSubtrees(html) {
  const out = [];
  const open = /<([a-z]+)\b[^>]*aria-hidden="true"[^>]*>/g;
  let match;
  while ((match = open.exec(html))) {
    const tag = match[1];
    let depth = 1;
    const re = new RegExp(`<(/?)${tag}\\b[^>]*?(/?)>`, "g");
    re.lastIndex = match.index + match[0].length;
    let end = html.length;
    let m;
    while ((m = re.exec(html))) {
      if (m[2] === "/") continue;
      depth += m[1] ? -1 : 1;
      if (depth === 0) {
        end = m.index + m[0].length;
        break;
      }
    }
    out.push(html.slice(match.index, end));
  }
  return out;
}

describe("Live guide names the channel in every cell (A11Y-001)", () => {
  it("every cell's accessible name starts with channel number and name", () => {
    const html = render();
    const rows = html.split('data-testid="live-guide-row"').slice(1);
    assert.equal(rows.length, guide.channels.length);
    rows.forEach((row, index) => {
      const label = guideChannelLabel(guide.channels[index]);
      const names = [...row.matchAll(/class="live-guide-cell[^"]*"[^>]*aria-label="([^"]*)"/g)].map((m) => m[1]);
      assert.equal(names.length, guide.channels[index].programs.length, `row ${index}`);
      for (const name of names) {
        assert.ok(name.startsWith(`${label}, `), `"${name}" should start with "${label}"`);
      }
    });
    assert.match(html, /aria-label="4 Drama, Heat, /);
    assert.match(html, /aria-label="12 Youth Safe, Paddington, /);
  });

  it("nothing inside aria-hidden is focusable", () => {
    const html = render();
    const hidden = ariaHiddenSubtrees(html);
    for (const chunk of hidden) {
      assert.doesNotMatch(chunk, /<(button|a|input|select|textarea)\b/, chunk.slice(0, 120));
      assert.doesNotMatch(chunk, /tabindex="(?!-1)/i, chunk.slice(0, 120));
    }
    // The station rail is exposed, so its tune buttons are reachable by name.
    assert.match(html, /aria-label="Tune 12 Youth Safe"/);
  });

  it("the guide container is a named, focusable group", () => {
    const html = render();
    assert.match(html, /<div class="live-guide"[^>]*role="group"[^>]*aria-label="Live guide"[^>]*tabindex="0"/);
  });

  it("guideChannelLabel tolerates a missing number", () => {
    assert.equal(guideChannelLabel({ number: 4, name: "Drama" }), "4 Drama");
    assert.equal(guideChannelLabel({ name: "Drama" }), "Drama");
    assert.equal(guideChannelLabel({ number: 0, name: "Zero" }), "0 Zero");
  });
});

describe("Live guide focus rings and type floor (A11Y-004, VIS-004)", () => {
  const css = readFileSync(join(src, "styles", "12-live.css"), "utf8");

  it("guide container, cells, and player draw an outline on :focus-visible", () => {
    for (const selector of [".live-guide:focus-visible", ".live-guide-cell:focus-visible", ".live-player:focus-visible"]) {
      const re = new RegExp(`${selector.replace(/[.]/g, "\\.")}[^{]*\\{[^}]*outline:\\s*2px solid`, "s");
      assert.match(css, re, selector);
    }
  });

  it("no Live rule outside the weather channel sets a literal font-size under 12px", () => {
    const offenders = [];
    for (const block of css.matchAll(/([^{}]+)\{([^}]*)\}/g)) {
      const selector = block[1].trim();
      if (/\.weather-/.test(selector)) continue;
      for (const m of block[2].matchAll(/font-size:\s*([0-9.]+)(rem|px)\b/g)) {
        const px = m[2] === "rem" ? Number(m[1]) * 15 : Number(m[1]);
        if (px < 12) offenders.push(`${selector}: ${m[0]}`);
      }
    }
    assert.deepEqual(offenders, []);
  });
});

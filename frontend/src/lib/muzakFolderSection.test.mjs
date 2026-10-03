import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { readAllStyles } from "./readStyles.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const advanced = readFileSync(join(here, "../pages/admin/LiveChannelsAdvanced.jsx"), "utf8");
const panel = readFileSync(join(here, "../components/admin/MuzakFolderPanel.jsx"), "utf8");
const styles = readAllStyles();

/** Source of the element that carries `data-testid`, including nested divs. */
function elementByTestId(source, testId) {
  const marker = `data-testid="${testId}"`;
  const at = source.indexOf(marker);
  assert.notEqual(at, -1, `missing ${testId}`);
  const open = source.lastIndexOf("<div", at);
  assert.notEqual(open, -1, `no opening div for ${testId}`);
  let depth = 0;
  for (let i = open; i < source.length; i += 1) {
    if (source.startsWith("<div", i)) {
      depth += 1;
    } else if (source.startsWith("</div>", i)) {
      depth -= 1;
      if (depth === 0) return source.slice(open, i + "</div>".length);
    }
  }
  throw new Error(`unclosed div for ${testId}`);
}

describe("Weather Channel music section", () => {
  it("is a sibling card after Between-show breaks, not inside the filler card", () => {
    const filler = elementByTestId(advanced, "live-channels-filler-paths");
    assert.match(filler, /live-channels-schedule-settings/);
    assert.match(filler, /live-channels-filler-add/);
    assert.doesNotMatch(filler, /MuzakFolderPanel/);
    assert.doesNotMatch(filler, /live-muzak-folder/);
    assert.doesNotMatch(filler, /Weather Channel music/);

    const fillerEnd = advanced.indexOf(filler) + filler.length;
    const musicAt = advanced.indexOf("<MuzakFolderPanel");
    const plexAt = advanced.indexOf('data-testid="live-channels-plex-attach"');
    assert.ok(musicAt > fillerEnd, "music panel should follow the filler card");
    assert.ok(plexAt > musicAt, "music panel should precede Plex Live TV");
  });

  it("uses its own service card and a single-column body, not the filler field grid", () => {
    assert.match(panel, /className="service-card live-channels-muzak-card"/);
    assert.match(panel, /className="service-card-header"[\s\S]*?<h3>Weather Channel music<\/h3>/);
    assert.match(panel, /data-testid="live-muzak-folder"/);
    assert.match(panel, /data-testid="live-muzak-clear"/);
    assert.match(panel, /data-testid="live-media-browser"/);
    assert.doesNotMatch(panel, /service-fields/);
    assert.match(
      styles,
      /\.live-channels-muzak-card\s*\{[^}]*margin-top:\s*var\(--space-4\)/s,
    );
    assert.match(
      styles,
      /\.muzak-folder-panel\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/s,
    );
    assert.doesNotMatch(styles, /\.muzak-folder-panel\s*\{[^}]*grid-column:\s*1\s*\/\s*-1/s);
  });
});

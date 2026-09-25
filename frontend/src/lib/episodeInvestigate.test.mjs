import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  SCENE_NAMES_NOT_EVIDENCE,
  STILLS_LEAVE_LAN,
  confidenceLabel,
  defaultRowSelected,
  selectedFileIds,
  selectionMap,
} from "./episodeInvestigate.js";

const here = dirname(fileURLToPath(import.meta.url));
const libraries = readFileSync(join(here, "../pages/admin/LibrariesSection.jsx"), "utf8");

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
});

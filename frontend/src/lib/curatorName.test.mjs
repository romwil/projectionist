import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  GENERIC_CURATOR_NAME,
  activeVoice,
  curatorDisplayName,
  curatorNameInSentence,
} from "./curatorName.ts";
import { chatErrorMessage } from "./chatSession.ts";
import { tonightOneLiner } from "./whatsOnTonight.ts";

const professor = { id: "academic-critic", name: "Academic Critic", nickname: "The Professor", is_default: true };
const host = { id: "host", name: "Host", nickname: "The Host" };

describe("curatorDisplayName (GRO-014)", () => {
  it("uses the owner's curator name when set", () => {
    assert.equal(curatorDisplayName({ curator_name: "Roger" }, professor), "Roger");
  });

  it("falls back to the voice the picker shows, not the stored default", () => {
    assert.equal(curatorDisplayName({ curator_name: "Curator" }, professor), "The Professor");
    assert.equal(curatorDisplayName(null, { name: "My Voice" }), "My Voice");
  });

  it("says Your curator when nothing is named", () => {
    assert.equal(curatorDisplayName({ curator_name: "Curator" }, null), GENERIC_CURATOR_NAME);
    assert.equal(curatorDisplayName(undefined, undefined), GENERIC_CURATOR_NAME);
    assert.equal(curatorNameInSentence(GENERIC_CURATOR_NAME), "your curator");
    assert.equal(curatorNameInSentence("Roger"), "Roger");
  });

  it("picks the selected voice, else the default one", () => {
    assert.equal(activeVoice([professor, host], "host"), host);
    assert.equal(activeVoice([host, professor], null), professor);
    assert.equal(activeVoice([], "host"), null);
  });

  it("generic copy never shows the bare stored default", () => {
    assert.doesNotMatch(tonightOneLiner({ ready: false }), /^Curator /);
    assert.match(chatErrorMessage("timeout", 0.5), /^Your curator couldn't respond/);
  });
});

describe("member-facing sources", () => {
  const srcDir = join(dirname(fileURLToPath(import.meta.url)), "..");
  // Owner Config preview and the reversed-name easter egg intentionally read the stored name.
  const allowed = new Set(["pages/ConfigPage.tsx", "hooks/useChatSession.ts", "lib/curatorName.ts"]);

  function walk(dir, out = []) {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full, out);
      else if (/\.(tsx?|jsx?)$/.test(entry) && !/\.test\./.test(entry)) out.push(full);
    }
    return out;
  }

  it("do not fall back to the literal \"Curator\"", () => {
    const offenders = walk(srcDir)
      .map((file) => file.slice(srcDir.length + 1))
      .filter((rel) => !allowed.has(rel))
      .filter((rel) => readFileSync(join(srcDir, rel), "utf8").includes('"Curator"'));
    assert.deepEqual(offenders, []);
  });
});

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { LIVE_ADMIN_GLOSSARY } from "./liveChannelsCopy.js";
import {
  GLOSSARY_FALLBACK_HELP,
  GLOSSARY_HELP,
  glossaryEntry,
  glossaryLabels,
  sectionHelpPlainBody,
} from "./glossary.js";

describe("glossary", () => {
  it("resolves ops keys through the Live Admin glossary", () => {
    const entry = glossaryEntry("Broadcast engine");
    assert.equal(entry.label, "TV engine");
    assert.match(entry.help, /Tunarr/i);
  });

  it("accepts craft labels directly", () => {
    const entry = glossaryEntry("Between-show breaks");
    assert.equal(entry.label, "Between-show breaks");
    assert.match(entry.help, /gaps between programs/i);
  });

  it("keeps help blurbs for every Live Admin glossary target", () => {
    for (const label of Object.values(LIVE_ADMIN_GLOSSARY)) {
      if (label === "TV engine running" || label === "TV engine unreachable" || label === "TV healthy") {
        continue; // status chips, not section terms
      }
      assert.ok(GLOSSARY_HELP[label], `missing GLOSSARY_HELP for “${label}”`);
    }
  });


  it("marks status-chip labels as known even without dedicated help blurbs", () => {
    const entry = glossaryEntry("TV engine running");
    assert.equal(entry.known, true);
    assert.equal(entry.label, "TV engine running");
    assert.equal(entry.help, null);
  });

  it("treats completely unknown keys as not known", () => {
    const entry = glossaryEntry("not-a-real-glossary-term");
    assert.equal(entry.known, false);
    assert.equal(entry.help, null);
    assert.equal(sectionHelpPlainBody("not-a-real-glossary-term"), null);
  });

  it("sectionHelpPlainBody keeps the (?) body for label-only known entries", () => {
    assert.equal(sectionHelpPlainBody("TV engine running"), GLOSSARY_FALLBACK_HELP);
    assert.equal(sectionHelpPlainBody("Broadcast engine running"), GLOSSARY_FALLBACK_HELP);
  });

  it("sectionHelpPlainBody returns dedicated help when present", () => {
    assert.match(sectionHelpPlainBody("Setup"), /Engine/);
    assert.match(sectionHelpPlainBody("Installation"), /Engine/);
  });

  it("lists unique sorted labels", () => {
    const labels = glossaryLabels();
    assert.ok(labels.includes("TV engine"));
    assert.ok(labels.includes("Setup"));
    assert.deepEqual(labels, [...labels].sort());
  });
});

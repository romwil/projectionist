import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  JOURNEY_CATALOG,
  assertNoEngagementCopy,
  buildJourneyNodes,
  buildJourneyTree,
  filterCatalogForYouth,
  memberFacingCopyOk,
  personaPathways,
  prerequisitesMet,
} from "./journeyAchievements.js";

describe("journeyAchievements", () => {
  it("ships a substantial catalog across tiers and categories", () => {
    assert.ok(JOURNEY_CATALOG.length >= 30);
    const tiers = new Set(JOURNEY_CATALOG.map((n) => n.tier));
    assert.ok(tiers.has("easy") && tiers.has("mid") && tiers.has("deep"));
    assert.ok(JOURNEY_CATALOG.some((n) => n.hidden));
    assert.ok(JOURNEY_CATALOG.some((n) => n.personaId));
    assert.ok(JOURNEY_CATALOG.some((n) => n.ultimate));
  });

  it("never uses the word engagement in member-facing copy", () => {
    for (const node of JOURNEY_CATALOG) {
      assertNoEngagementCopy(node.name);
      assertNoEngagementCopy(node.description);
      assertNoEngagementCopy(node.teaser || "");
    }
    const nodes = buildJourneyNodes({ badges: [] });
    assert.equal(memberFacingCopyOk(nodes), true);
  });

  it("hides locked secret names until earned", () => {
    const nodes = buildJourneyNodes({ badges: [] });
    const secret = nodes.find((n) => n.id === "secret-konami");
    assert.equal(secret.displayName, "???");
    const earned = buildJourneyNodes({
      badges: [{ slug: "secret-konami" }],
    });
    assert.notEqual(earned.find((n) => n.id === "secret-konami").displayName, "???");
  });

  it("respects persona pathway prerequisites", () => {
    const catalog = JOURNEY_CATALOG;
    const switchNode = catalog.find((n) => n.id === "concierge-persona-switch");
    const earnedEmpty = new Set();
    assert.equal(prerequisitesMet(switchNode, earnedEmpty, catalog), false);
    const earnedAsk = new Set(["story-explorer"]);
    assert.equal(prerequisitesMet(switchNode, earnedAsk, catalog), true);
  });

  it("filters youth-unsafe nodes", () => {
    const youth = filterCatalogForYouth(JOURNEY_CATALOG, true);
    assert.ok(youth.every((n) => n.youthSafe !== false));
    assert.ok(youth.length < JOURNEY_CATALOG.length);
  });

  it("builds Civ-style tree columns and persona pathways", () => {
    const nodes = buildJourneyNodes({
      badges: [{ slug: "first-review" }, { slug: "story-explorer" }],
    });
    const tree = buildJourneyTree(nodes);
    assert.ok(tree.length >= 5);
    assert.ok(tree.every((col) => col.nodes.length));
    const paths = personaPathways(nodes);
    assert.ok(paths.some((p) => p.personaId === "night-owl" || p.personaId === "critic"));
  });
});

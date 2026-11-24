import assert from "node:assert/strict";
import test from "node:test";

import {
  addShelfIdFirst,
  curateClickPlan,
  holidaySummary,
  inputToTerms,
  moveShelfId,
  observanceListState,
  seasonalCardMeta,
  seasonalPickChatSeed,
  seasonalRailTitle,
  shelfDateLabel,
  shelfFormFromItem,
  shelfPatchFromForm,
  shelfRoleLabel,
  visibleCuratedShelf,
} from "./seasonalShelves.ts";

test("moveShelfId moves one row and clamps at the ends", () => {
  assert.deepEqual(moveShelfId([1, 2, 3], 2, -1), [1, 3, 2]);
  assert.deepEqual(moveShelfId([1, 2, 3], 0, -1), [1, 2, 3]);
  assert.deepEqual(moveShelfId([1, 2, 3], 2, 1), [1, 2, 3]);
  assert.deepEqual(moveShelfId([1, 2, 3], 0, 1), [2, 1, 3]);
});

test("addShelfIdFirst puts a title at the front without duplicating it", () => {
  assert.deepEqual(addShelfIdFirst([4, 5, 6], 9), [9, 4, 5, 6]);
  assert.deepEqual(addShelfIdFirst([4, 5, 6], 5), [5, 4, 6]);
});

test("shelfDateLabel reads fixed and movable bindings", () => {
  assert.equal(shelfDateLabel({ kind: "fixed", month: 10, day: 31 }), "Oct 31");
  assert.equal(
    shelfDateLabel({ kind: "movable", movable_rule: "thanksgiving" }),
    "Fourth Thursday of November",
  );
  assert.equal(shelfDateLabel(null), "");
});

test("patch carries retitle, terms, shoulders, enabled; movable shelves keep their rule", () => {
  const fixed = { kind: "fixed", month: 10, day: 31, name: "Halloween" };
  const form = {
    ...shelfFormFromItem(fixed),
    name: "  Spooky season ",
    month: "10",
    day: "30",
    search_terms: "horror, haunted\nwitch",
    pre_shoulder_days: "14",
    enabled: false,
  };
  assert.deepEqual(shelfPatchFromForm(form, fixed), {
    name: "Spooky season",
    pre_shoulder_days: 14,
    post_shoulder_days: 2,
    search_terms: ["horror", "haunted", "witch"],
    enabled: false,
    month: 10,
    day: 30,
  });
  const movable = { kind: "movable", movable_rule: "thanksgiving" };
  const patch = shelfPatchFromForm(shelfFormFromItem(movable), movable);
  assert.equal("month" in patch, false);
  assert.deepEqual(inputToTerms(" a, ,b "), ["a", "b"]);
});

test("role labels are plain language", () => {
  assert.equal(shelfRoleLabel("pin"), "Picked by you");
  assert.equal(shelfRoleLabel(undefined), "Matches the season");
  assert.equal(shelfRoleLabel("match", { hasNote: true }), "Staff pick");
});

test("seasonal pick chat seed carries season, title, and curator note", () => {
  const seed = seasonalPickChatSeed({
    seasonLabel: "Halloween",
    scopeId: "halloween",
    title: "Evil Dead Burn",
    year: 2026,
    curatorNote: "A lean gateway scream for newcomers.",
    railRole: "pin",
  });
  assert.match(seed, /Halloween seasonal picks on Explore/);
  assert.match(seed, /Evil Dead Burn/);
  assert.match(seed, /2026/);
  assert.match(seed, /lean gateway scream/);
  assert.match(seed, /professor/);
  assert.match(seed, /halloween/);
});

test("curate click applies picks for both seasons and surfaces a failure", () => {
  const halloween = curateClickPlan({
    proposal: {
      picks: [
        { library_item_id: 11, curator_note: "The doorway this year." },
        { library_item_id: 12, note: "The quieter one." },
      ],
    },
  });
  assert.equal(halloween.ok, true);
  assert.equal(halloween.stage, "preview");
  assert.deepEqual(halloween.applyPicks, [
    { library_item_id: 11, curator_note: "The doorway this year." },
    { library_item_id: 12, curator_note: "The quieter one." },
  ]);

  const muertos = curateClickPlan({
    proposal: {
      picks: [{ library_item_id: 21, curator_note: "Why this ofrenda this year." }],
    },
  });
  assert.equal(muertos.ok, true);
  assert.equal(muertos.applyPicks[0].library_item_id, 21);

  const failed = curateClickPlan({ error: "Curator request failed: model timeout" });
  assert.equal(failed.ok, false);
  assert.match(failed.message, /model timeout/);
  assert.deepEqual(failed.applyPicks, []);

  const empty = curateClickPlan({ proposal: { picks: [] } });
  assert.equal(empty.ok, false);
  assert.match(empty.message, /didn't return any picks/);

  const blankNote = curateClickPlan({
    proposal: {
      theme: "Snowed in",
      picks: [{ library_item_id: 4, curator_note: "   ", role: "Deep cut" }],
    },
  });
  assert.equal(blankNote.ok, false);
});

test("a proposal keeps the theme, role, and why it matched for the preview", () => {
  const plan = curateClickPlan({
    proposal: {
      theme: "Letters and one late sitting",
      picks: [
        {
          library_item_id: 7,
          note: "The visit the household already quotes.",
          role: "Classic",
          matched_because: "Keyword christmas.",
        },
      ],
    },
  });
  assert.equal(plan.stage, "preview");
  assert.equal(plan.theme, "Letters and one late sitting");
  assert.deepEqual(plan.applyPicks[0], {
    library_item_id: 7,
    curator_note: "The visit the household already quotes.",
    role: "Classic",
    matched_because: "Keyword christmas.",
  });
});

test("Explore titles the rail with the theme, and the list states stay plain", () => {
  assert.equal(
    seasonalRailTitle({ label: "Christmas", theme: "Letters and snow" }),
    "Christmas — Letters and snow",
  );
  assert.equal(seasonalRailTitle({ label: "Christmas" }), "Christmas");
  assert.equal(observanceListState({ id: "christmas", enabled: false }, []), "Off");
  assert.equal(
    observanceListState({ id: "christmas", enabled: true }, [{ id: "christmas", active_now: true }]),
    "On Explore now",
  );
  assert.equal(observanceListState({ id: "christmas", enabled: true }, []), "Coming up");
  assert.equal(
    holidaySummary({
      item: { id: "christmas", schedule_publish: true, grounding_date_label: "Dec 25" },
      schedule: [{ id: "christmas", window_start: "2026-12-04", window_end: "2026-12-29" }],
      shelfCount: 10,
    }),
    "2026-12-04 – 2026-12-29 · 10 on the shelf · Live block on",
  );
});

test("a curated shelf drops old keyword cards; a hand pin does not", () => {
  const items = [
    { id: 1, rail_role: "pin", curator_note: "Why this year." },
    { id: 2, rail_role: "match", title: "Year sort dump" },
    { id: 3, rail_role: "include", title: "Added by you" },
  ];
  assert.deepEqual(
    visibleCuratedShelf(items, { replacesMatches: true }).map((row) => row.id),
    [1, 3],
  );
  assert.deepEqual(
    visibleCuratedShelf(items, { replacesMatches: false }).map((row) => row.id),
    [1, 2, 3],
  );
});

test("seasonal card meta prefers curator notes for Explore posters", () => {
  assert.equal(
    seasonalCardMeta({ curator_note: "Staff pick for spooky season.", why: "fallback" }),
    "Staff pick for spooky season.",
  );
  assert.equal(seasonalCardMeta({ why: "Only why" }), "Only why");
  assert.equal(seasonalCardMeta({ anniversary_text: "Released today" }), "Released today");
  assert.equal(seasonalCardMeta({}), null);
});

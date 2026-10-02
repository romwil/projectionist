import assert from "node:assert/strict";
import test from "node:test";

import {
  addShelfIdFirst,
  inputToTerms,
  moveShelfId,
  shelfDateLabel,
  shelfFormFromItem,
  shelfPatchFromForm,
  shelfRoleLabel,
} from "./seasonalShelves.js";

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
});

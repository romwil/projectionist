import assert from "node:assert/strict";
import test from "node:test";

import { PREPARE_FOR_SCREEN, offersCopy } from "./prepareForScreen.ts";

test("the member sees the preparing sentence and an offer to make a copy", () => {
  assert.equal(offersCopy(PREPARE_FOR_SCREEN), true);
  assert.equal(offersCopy(`  ${PREPARE_FOR_SCREEN}  `), true);
  assert.equal(offersCopy("Plex is unreachable."), false);
  assert.equal(PREPARE_FOR_SCREEN, "This title needs preparing for this screen");
});

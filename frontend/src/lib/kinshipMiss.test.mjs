import assert from "node:assert/strict";
import test from "node:test";

import { formatKinshipMissHit, kinshipMissWhyLabel } from "./kinshipMiss.js";

test("kinshipMissWhyLabel maps stored and public why codes", () => {
  assert.equal(kinshipMissWhyLabel("more_like_this_empty"), "Empty More Like This");
  assert.equal(kinshipMissWhyLabel("related_empty"), "Empty Related titles");
  assert.equal(kinshipMissWhyLabel("relations_empty"), "Empty Related titles");
  assert.equal(kinshipMissWhyLabel("bridge_zero_peers"), "Bridge with zero peers");
});

test("formatKinshipMissHit is demand, not a grade", () => {
  assert.equal(formatKinshipMissHit(1), "1 miss");
  assert.equal(formatKinshipMissHit(3), "3 misses");
});

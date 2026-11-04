import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  ERASE_CONFIRM_PHRASE,
  erasePhraseMatches,
  erasedSummary,
  exportMyDataUrl,
  noteKindLabel,
} from "./myData.ts";

const root = join(dirname(fileURLToPath(import.meta.url)), "../../..");

test("confirm phrase matches the server's phrase", () => {
  const routes = readFileSync(join(root, "projectionist/web/auth_routes.py"), "utf8");
  assert.match(routes, new RegExp(`ERASE_CONFIRM_PHRASE = "${ERASE_CONFIRM_PHRASE}"`));
  assert.ok(erasePhraseMatches("  Delete My Data "));
  assert.ok(!erasePhraseMatches("delete"));
  assert.ok(!erasePhraseMatches(""));
});

test("exports use the signed-in account route, never a user id", () => {
  assert.equal(exportMyDataUrl("json"), "/api/me/memory?format=json");
  assert.equal(exportMyDataUrl("markdown"), "/api/me/memory?format=markdown");
});

test("copy stays plain", () => {
  assert.equal(noteKindLabel("watch_intention"), "Plans to watch");
  assert.equal(noteKindLabel("something_new"), "Something new");
  assert.equal(erasedSummary(0), "There was nothing to delete.");
  assert.equal(erasedSummary(1), "Deleted 1 item. Your account is still here.");
});

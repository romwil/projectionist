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
  ownerAccessLine,
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

test("owner-access log lines name who did what, and flag refused attempts (PRIV-023)", () => {
  const at = Date.UTC(2026, 0, 3, 12) / 1000;
  assert.equal(
    ownerAccessLine({ created_at: at, event: "youth_change", label: "Changed Youth mode on your account", actor_name: "Alex" }, "en-US"),
    "Jan 3, 2026 — Alex: Changed Youth mode on your account",
  );
  assert.equal(
    ownerAccessLine({ created_at: at, event: "memory_review", label: "Opened the Youth memory review for your account" }, "en-US"),
    "Jan 3, 2026 — The owner: Opened the Youth memory review for your account",
  );
  assert.match(
    ownerAccessLine({ created_at: at, event: "role_change", label: "Changed your role", outcome: "denied" }, "en-US"),
    /\(not allowed\)$/,
  );
  const page = readFileSync(join(root, "frontend/src/pages/settings/MyDataPage.tsx"), "utf8");
  assert.match(page, /testId="my-data-owner-access"/);
  assert.match(page, /listMyOwnerAccess\(\)/);
});

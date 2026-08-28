import assert from "node:assert/strict";
import test from "node:test";
import {
  filterSlashCommandPalette,
  formatSlashCommandInsert,
  shouldShowSlashCommandPalette,
} from "./slashCommandPalette.js";

test("slash command palette", () => {
  assert.ok(filterSlashCommandPalette("/").length > 0);
  assert.equal(formatSlashCommandInsert("help"), "/help ");
  assert.equal(shouldShowSlashCommandPalette("/stats "), false);
});

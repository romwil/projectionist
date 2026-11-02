import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = join(dirname(fileURLToPath(import.meta.url)), "../../..");
const privacyPath = join(root, "docs/PRIVACY.md");

test("docs/PRIVACY.md ships required disclosure anchors and matrices", () => {
  const markdown = readFileSync(privacyPath, "utf8");
  assert.ok(markdown.length > 500, "privacy markdown must not be empty");
  assert.match(markdown, /#household-members/);
  assert.match(markdown, /#server-owners/);
  assert.match(markdown, /#mcp/);
  assert.match(markdown, /## From the household member/);
  assert.match(markdown, /## From the server owner/);
  assert.match(markdown, /## MCP \(Model Context Protocol\)/);
  assert.match(markdown, /## Exposure matrices/);
  assert.match(markdown, /## We do not/);
  assert.match(markdown, /Privacy MCP/);
  assert.match(markdown, /Full MCP|full MCP|Full \/ in-stack/i);
  assert.match(markdown, /voice|SpeechRecognition|speechSynthesis/i);
  assert.match(markdown, /preferred (conversation )?name/i);
  assert.match(markdown, /watchlist/i);
  assert.match(markdown, /image\.tmdb\.org|TMDB/);
  assert.match(markdown, /X-Plex-Token/);
});

test("docs/PRIVACY.md drops claims the code does not keep (PRIV-002)", () => {
  const markdown = readFileSync(privacyPath, "utf8");
  assert.doesNotMatch(markdown, /full copy of its own data/i);
  assert.doesNotMatch(markdown, /Leave anything behind/i);
  assert.doesNotMatch(markdown, /Email household invites/i);
  assert.doesNotMatch(markdown, /verified in `projectionist/);
  assert.doesNotMatch(markdown, /link-based/i);
  assert.doesNotMatch(markdown, /sanitized media research/i);
  assert.doesNotMatch(markdown, /who can run it for your account/i);
  assert.match(markdown, /newsletter/i);
  assert.match(markdown, /Resend/);
  assert.match(markdown, /embeddings provider/i);
  assert.match(markdown, /never joined/i);
  assert.match(markdown, /Youth accounts use the same provider/);
  assert.match(markdown, /Asking to join/);
  assert.match(markdown, /What removal leaves behind/);
});

test("member half of docs/PRIVACY.md has no API paths or config keys", () => {
  const markdown = readFileSync(privacyPath, "utf8");
  const start = markdown.indexOf("## From the household member");
  const end = markdown.indexOf("## From the server owner");
  assert.ok(start >= 0 && end > start);
  const memberHalf = markdown.slice(start, end);
  assert.doesNotMatch(memberHalf, /\/api\//);
  assert.doesNotMatch(memberHalf, /PROJECTIONIST_[A-Z_]+/);
  assert.doesNotMatch(memberHalf, /settings\.json/);
});

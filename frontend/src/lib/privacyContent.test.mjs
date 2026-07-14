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

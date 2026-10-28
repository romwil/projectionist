import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { inboxFollowUpParams, INBOX_FIRST_PAINT_LIMIT, INBOX_FIRST_PAINT_PARAMS, INBOX_LIST_PARAMS } from "./recommendationInbox.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

test("inbox first paint is a short unread page, then older rows", () => {
  assert.equal(INBOX_FIRST_PAINT_PARAMS.unread_only, true);
  assert.equal(INBOX_FIRST_PAINT_PARAMS.limit, INBOX_FIRST_PAINT_LIMIT);
  assert.ok(INBOX_FIRST_PAINT_LIMIT < INBOX_LIST_PARAMS.limit);

  assert.equal(inboxFollowUpParams(3, 3), null);
  assert.equal(inboxFollowUpParams(INBOX_FIRST_PAINT_LIMIT, INBOX_FIRST_PAINT_LIMIT), null);
  assert.deepEqual(inboxFollowUpParams(INBOX_FIRST_PAINT_LIMIT, 40), {
    unread_only: true,
    limit: INBOX_LIST_PARAMS.limit - INBOX_FIRST_PAINT_LIMIT,
    offset: INBOX_FIRST_PAINT_LIMIT,
  });
});

test("inbox page paints before auth and does not load the full unread window first", () => {
  const page = readFileSync(join(root, "pages/InboxPage.tsx"), "utf8");
  assert.match(page, /blockUntilAuth=\{false\}/);
  assert.match(page, /inboxListParams/);
  assert.doesNotMatch(page, /if \(!authReady\)/);
  assert.doesNotMatch(page, /inbox-auth-loading/);
  assert.doesNotMatch(page, /listNotifications\(INBOX_LIST_PARAMS\)/);
  assert.doesNotMatch(page, /if \(!authReady \|\|/);
  assert.doesNotMatch(page, /setActiveSession/);
  assert.doesNotMatch(page, /ROUTES\.chat/);
  assert.doesNotMatch(page, /chatAboutTitleHref/);
});

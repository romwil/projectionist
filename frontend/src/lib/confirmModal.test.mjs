import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { readAllStyles } from "./readStyles.mjs";
import {
  YIR_SELF_GENERATE_CONFIRM,
  YIR_SELF_GENERATE_PAYLOAD,
  runConfirmedYirGenerate,
  yirAdminGenerateConfirmOptions,
} from "./yearInReview.ts";
import { newsletterConfirmOptions } from "./weeklyNewsletter.ts";
import { seerrSyncConfirmOptions } from "./seerrHousehold.ts";

const here = dirname(fileURLToPath(import.meta.url));
const srcRoot = join(here, "..");

function walkJsx(dir, acc = []) {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === "dist") continue;
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) walkJsx(full, acc);
    else if (/\.(jsx|js|tsx|ts)$/.test(name)) acc.push(full);
  }
  return acc;
}

describe("ConfirmModal chrome", () => {
  const modal = readFileSync(join(srcRoot, "components", "ConfirmModal.tsx"), "utf8");
  const hook = readFileSync(join(srcRoot, "hooks", "useConfirmModal.tsx"), "utf8");
  const styles = readAllStyles();

  it("reuses RecommendModal overlay chrome, not a native dialog", () => {
    assert.match(modal, /className="recommend-modal-backdrop"/);
    assert.match(modal, /className="recommend-modal confirm-modal"/);
    assert.match(modal, /role="dialog"/);
    assert.match(modal, /aria-modal="true"/);
    assert.match(modal, /className="ghost"/);
    assert.match(modal, /className=\{danger \? "primary danger" : "primary"\}/);
    assert.equal(/<dialog[\s>]/.test(modal), false, "must not use native <dialog>");
    assert.equal(/window\.confirm/.test(modal), false);
    assert.match(hook, /from "\.\.\/components\/ConfirmModal"/);
  });

  it("traps focus and cancels on Escape / overlay click", () => {
    assert.match(modal, /event\.key === "Escape"/);
    assert.match(modal, /event\.key !== "Tab"/);
    assert.match(modal, /onClick=\{onCancel\}/);
    assert.match(modal, /data-testid="confirm-modal-cancel"/);
    assert.match(modal, /data-testid="confirm-modal-confirm"/);
  });

  it("hosts an in-app prompt field instead of window.prompt", () => {
    assert.match(modal, /data-testid="confirm-modal-prompt"/);
    assert.match(hook, /prompt: options\.prompt \|\| null/);
    assert.match(styles, /\.confirm-modal-field\s*\{/);
    assert.equal(/window\.prompt\s*\(/.test(modal), false);
    assert.equal(/window\.prompt\s*\(/.test(hook), false);
  });

  it("keeps dimmed-stage + danger primary in the shared overlay stylesheet", () => {
    assert.match(styles, /\.recommend-modal-backdrop\s*\{/);
    assert.match(styles, /\.recommend-modal\.confirm-modal\s*\{/);
    assert.match(styles, /\.confirm-modal-copy\s*\{/);
    assert.match(styles, /\.recommend-modal-actions \.primary\.danger\s*\{/);
  });
});

describe("YIR generate confirm", () => {
  const notifications = readFileSync(
    join(srcRoot, "pages", "settings", "NotificationsSettingsPage.tsx"),
    "utf8",
  );

  it("does not call window.confirm from member Notifications", () => {
    assert.equal(
      /window\.confirm/.test(notifications),
      false,
      "NotificationsSettingsPage must not use window.confirm",
    );
    assert.match(notifications, /useConfirmModal/);
    assert.match(notifications, /YIR_SELF_GENERATE_CONFIRM/);
    assert.match(notifications, /runConfirmedYirGenerate/);
  });

  it("fires generateYearInReview with the same payload when confirmed", async () => {
    assert.deepEqual(YIR_SELF_GENERATE_PAYLOAD, { scope: "self", notify: true });
    assert.match(YIR_SELF_GENERATE_CONFIRM.body, /Year in Review reel now/);
    const calls = [];
    const snap = { job: "yir-1" };
    const result = await runConfirmedYirGenerate({
      confirmed: true,
      generate: async (payload) => {
        calls.push(payload);
        return snap;
      },
    });
    assert.deepEqual(calls, [{ scope: "self", notify: true }]);
    assert.equal(result, snap);
  });

  it("does not call the generate API when cancelled", async () => {
    let called = 0;
    const result = await runConfirmedYirGenerate({
      confirmed: false,
      generate: async () => {
        called += 1;
        return { job: "nope" };
      },
    });
    assert.equal(called, 0);
    assert.equal(result, null);
  });

  it("keeps newsletter send-to-me on the same in-app confirm path", () => {
    assert.match(notifications, /newsletterConfirmOptions\("self"\)/);
    const opts = newsletterConfirmOptions("self");
    assert.match(opts.title, /newsletter/i);
    assert.match(opts.body, /opted in/i);
    assert.equal(opts.confirmLabel, "Send");
  });

  it("varies admin YIR body with the notify toggle", () => {
    assert.match(yirAdminGenerateConfirmOptions(true).body, /notify your inbox/);
    assert.match(yirAdminGenerateConfirmOptions(false).body, /without sending a notification/);
  });
});

describe("no mixed native confirms", () => {
  it("leaves no window.confirm or window.prompt in frontend/src", () => {
    const hits = [];
    for (const file of walkJsx(srcRoot)) {
      const text = readFileSync(file, "utf8");
      if (/\bwindow\.(confirm|prompt)\s*\(/.test(text)) hits.push(file.slice(srcRoot.length + 1));
    }
    assert.deepEqual(hits, []);
  });

  it("puts Config Seerr token paste on ConfirmModal", () => {
    const config = readFileSync(join(srcRoot, "pages", "ConfigPage.tsx"), "utf8");
    const household = readFileSync(join(srcRoot, "pages", "admin", "HouseholdSection.tsx"), "utf8");
    assert.match(config, /seerrSyncConfirmOptions/);
    assert.match(config, /handleRotateMcpKey/);
    assert.match(config, /useConfirmModal/);
    assert.equal(/\bwindow\.prompt\s*\(/.test(config), false);
    assert.match(household, /handleUserSyncSeerr/);
    const opts = seerrSyncConfirmOptions("Ada");
    assert.equal(opts.title, "Sync Seerr account");
    assert.match(opts.body, /Ada/);
    assert.equal(opts.prompt.type, "password");
    assert.equal(opts.confirmLabel, "Sync");
  });
});

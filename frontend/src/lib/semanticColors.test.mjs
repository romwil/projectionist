import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";

const styles = join(dirname(fileURLToPath(import.meta.url)), "..", "styles");
const css = readdirSync(styles)
  .filter((name) => name.endsWith(".css"))
  .map((name) => readFileSync(join(styles, name), "utf8"))
  .join("\n");

/** Status and decorative rules on the screens trust phase 4 touched (VIS-002). */
const PHASE4_STATUS_SELECTORS = [
  ".title-card-pin",
  ".title-card-pin.pinned",
  ".inline-alert-error",
  ".inline-alert-success",
  ".user-status-pill.disabled",
  ".thread-delete-confirm",
  ".user-review-badge",
  ".recommend-modal-actions .primary.danger",
  ".message.error .message-inner",
  ".watch-progress-badge.is-partial::before",
  ".glass-door--halt .glass-door-card",
  ".primary-bottom-nav-badge",
  ".inbox-unread-badge",
  ".status.status-error",
  ".settings-channel-badge.is-owner-required",
  ".scheduled-tasks-execution-log-row.status-error",
];

const LITERAL = /#[0-9a-fA-F]{3,8}\b|rgba?\(\s*\d|hsla?\(\s*\d/;
const HUE_PROPS = /^(color|background(-color)?|border(-[a-z]+)*|fill|stroke|outline(-color)?)$/;

function rulesFor(selector) {
  const out = [];
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const selectors = m[1].split(",").map((s) => s.replace(/\/\*[\s\S]*?\*\//g, "").trim());
    if (selectors.includes(selector)) out.push(m[2]);
  }
  return out;
}

describe("semantic color tokens (VIS-002)", () => {
  it("every theme defines --danger, --success, --warning, --on-danger, and --star", () => {
    const blocks = [
      css.match(/:root\s*\{([^}]*)\}/)?.[1],
      css.match(/html\[data-theme="lights-down"\]\s*\{([^}]*)\}/)?.[1],
      css.match(/html\[data-theme="lights-up"\]\s*\{([^}]*)\}/)?.[1],
    ];
    for (const block of blocks) {
      assert.ok(block, "theme block missing");
      for (const token of ["--danger", "--success", "--warning", "--on-danger", "--star"]) {
        assert.match(block, new RegExp(`${token}:`), `${token} missing from a theme`);
      }
    }
  });

  for (const selector of PHASE4_STATUS_SELECTORS) {
    it(`${selector} uses tokens for status and decorative hues`, () => {
      const rules = rulesFor(selector);
      assert.ok(rules.length > 0, `no rule for ${selector}`);
      for (const body of rules) {
        for (const decl of body.split(";")) {
          const [prop, ...rest] = decl.split(":");
          const name = (prop || "").trim();
          if (!HUE_PROPS.test(name)) continue;
          const value = rest.join(":");
          assert.doesNotMatch(value, LITERAL, `${selector} { ${decl.trim()} }`);
        }
      }
    });
  }
});

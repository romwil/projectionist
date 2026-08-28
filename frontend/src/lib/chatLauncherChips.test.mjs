import assert from "node:assert/strict";
import test from "node:test";
import { CHAT_LAUNCHER_CHIPS, resolveChatLauncherChipAction } from "./chatLauncherChips.js";

test("chat launcher chips", () => {
  assert.equal(CHAT_LAUNCHER_CHIPS.length, 3);
  assert.equal(resolveChatLauncherChipAction(CHAT_LAUNCHER_CHIPS[2]).type, "prefill");
});

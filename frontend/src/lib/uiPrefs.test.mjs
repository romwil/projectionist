import assert from "node:assert/strict";
import test from "node:test";
import {
  applyUiTheme,
  cycleUiTheme,
  normalizeUiFontSize,
  normalizeUiTheme,
  resolveEffectiveTheme,
  themeControlIcon,
  themePreferenceLabel,
  themeToDataAttr,
} from "./uiPrefs.js";

test("normalizeUiFontSize accepts small medium large", () => {
  assert.equal(normalizeUiFontSize("small"), "small");
  assert.equal(normalizeUiFontSize("medium"), "medium");
  assert.equal(normalizeUiFontSize("large"), "large");
});

test("normalizeUiFontSize defaults invalid values to medium", () => {
  assert.equal(normalizeUiFontSize("huge"), "medium");
  assert.equal(normalizeUiFontSize(null), "medium");
  assert.equal(normalizeUiFontSize(undefined), "medium");
});

test("normalizeUiTheme accepts lights_up lights_down system", () => {
  assert.equal(normalizeUiTheme("lights_up"), "lights_up");
  assert.equal(normalizeUiTheme("lights_down"), "lights_down");
  assert.equal(normalizeUiTheme("system"), "system");
});

test("normalizeUiTheme defaults invalid values to system", () => {
  assert.equal(normalizeUiTheme("dark"), "system");
  assert.equal(normalizeUiTheme(null), "system");
  assert.equal(normalizeUiTheme(""), "system");
});

test("resolveEffectiveTheme passes through explicit prefs", () => {
  assert.equal(resolveEffectiveTheme("lights_up"), "lights_up");
  assert.equal(resolveEffectiveTheme("lights_down"), "lights_down");
});

test("resolveEffectiveTheme uses matchMedia for system", () => {
  assert.equal(resolveEffectiveTheme("system", { matches: true }), "lights_up");
  assert.equal(resolveEffectiveTheme("system", { matches: false }), "lights_down");
  assert.equal(
    resolveEffectiveTheme("system", (q) => ({ matches: q.includes("light") })),
    "lights_up",
  );
});

test("themeToDataAttr maps underscores to hyphenated data-theme", () => {
  assert.equal(themeToDataAttr("lights_up"), "lights-up");
  assert.equal(themeToDataAttr("lights_down"), "lights-down");
});

test("cycleUiTheme rotates preference order", () => {
  assert.equal(cycleUiTheme("lights_up"), "lights_down");
  assert.equal(cycleUiTheme("lights_down"), "system");
  assert.equal(cycleUiTheme("system"), "lights_up");
});

test("themePreferenceLabel and themeControlIcon", () => {
  assert.equal(themePreferenceLabel("lights_up"), "Lights Up");
  assert.equal(themePreferenceLabel("lights_down"), "Lights Down");
  assert.equal(themePreferenceLabel("system"), "Match system");
  assert.equal(themeControlIcon("system"), "brightness_auto");
  assert.equal(themeControlIcon("lights_up"), "light_mode");
  assert.equal(themeControlIcon("lights_down"), "dark_mode");
});

test("applyUiTheme persists preference without document", () => {
  const store = new Map();
  const storage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, v),
  };
  const result = applyUiTheme("lights_up", { storage, media: { matches: false } });
  assert.equal(result.preference, "lights_up");
  assert.equal(result.effective, "lights_up");
  assert.equal(store.get("curatorx.ui_theme"), "lights_up");
});

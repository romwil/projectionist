import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  appriseTestResultMessage,
  appriseUrlsLabel,
  mailTestResultMessage,
  savedSecretLabel,
} from "./mailSettingsUi.js";

describe("mailSettingsUi helpers", () => {
  it("labels saved secrets", () => {
    assert.equal(savedSecretLabel("Password", false), "Password");
    assert.equal(
      savedSecretLabel("Password", true),
      "Password (saved — leave blank to keep)",
    );
  });

  it("labels Apprise URL field with saved count", () => {
    assert.equal(appriseUrlsLabel({}), "Apprise URLs");
    assert.equal(
      appriseUrlsLabel({ urls_set: true, url_count: 2 }),
      "Apprise URLs (2 saved — leave blank to keep)",
    );
  });

  it("summarizes test results", () => {
    assert.equal(
      appriseTestResultMessage({ notified: 1 }),
      "Apprise test notified 1 destination.",
    );
    assert.equal(
      appriseTestResultMessage({ notified: 3 }),
      "Apprise test notified 3 destinations.",
    );
    assert.equal(
      mailTestResultMessage({ to_email: "a@b.co" }),
      "Test email sent to a@b.co.",
    );
    assert.match(mailTestResultMessage({}), /notification address/);
  });
});

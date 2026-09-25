import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  adminCanCancel,
  adminDisplayPercent,
  adminItemStatusLabel,
  adminPhaseLabel,
  adminProgressLine,
  adminShouldShowCard,
} from "./adminExecution.js";

const here = dirname(fileURLToPath(import.meta.url));
const configPage = readFileSync(join(here, "../pages/ConfigPage.jsx"), "utf8");
const libraries = readFileSync(join(here, "../pages/admin/LibrariesSection.jsx"), "utf8");
const client = readFileSync(join(here, "../api/client.js"), "utf8");
const help = readFileSync(join(here, "../../../docs/HELP.md"), "utf8");

describe("admin execution card helpers", () => {
  it("never treats a remaining queue as 100%", () => {
    const job = {
      phase: "registering",
      busy: true,
      percent: 80,
      execution: { queued: 2, running: 1, completed: 3, failed: 0, total: 6, percent: 50 },
    };
    assert.equal(adminDisplayPercent(job), 50);
    assert.equal(adminCanCancel(job), true);
    assert.match(adminProgressLine(job), /2 queued/);
    assert.match(adminProgressLine(job), /1 running/);
  });

  it("labels Radarr item outcomes", () => {
    assert.equal(adminItemStatusLabel({ status: "running" }), "in flight");
    assert.equal(adminItemStatusLabel({ status: "completed", outcome: "registered" }), "registered");
    assert.equal(adminItemStatusLabel({ status: "skipped", outcome: "already" }), "already in Radarr");
    assert.equal(adminItemStatusLabel({ status: "failed", outcome: "path_conflict" }), "path conflict");
    assert.equal(adminItemStatusLabel({ status: "failed" }), "failed");
    assert.equal(adminPhaseLabel("registering"), "Registering");
  });

  it("hides idle cards until work starts", () => {
    assert.equal(adminShouldShowCard({ phase: "idle", message: "Ready when you are" }), false);
    assert.equal(adminShouldShowCard({ phase: "queued", busy: true }), true);
  });

  it("wires Register in Radarr status poll + cancel", () => {
    assert.match(client, /export async function getRadarrRegisterStatus/);
    assert.match(client, /\/admin\/radarr\/register-existing\/status/);
    assert.match(client, /export async function cancelRadarrRegister/);
    assert.match(libraries, /testId="radarr-register-progress"/);
    assert.match(libraries, /AdminExecutionCard/);
    assert.match(configPage, /getRadarrRegisterStatus/);
  });

  it("HELP explains Register in Radarr live queue", () => {
    assert.match(help, /Register up to 25 in Radarr/);
    assert.match(help, /queued/);
    assert.match(help, /Cancel remaining/);
  });
});

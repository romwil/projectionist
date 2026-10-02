import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { readAllStyles } from "./readStyles.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const styles = readAllStyles();
const configPage = [
  readFileSync(join(here, "../pages/ConfigPage.jsx"), "utf8"),
  readFileSync(join(here, "../pages/admin/OverviewSection.jsx"), "utf8"),
  readFileSync(join(here, "../pages/admin/ConnectionsSection.jsx"), "utf8"),
  readFileSync(join(here, "../pages/admin/LibrariesSection.jsx"), "utf8"),
].join("\n");
const holidaysPage = readFileSync(join(here, "../pages/HolidaysPage.jsx"), "utf8");
const tasksPage = readFileSync(join(here, "../pages/ScheduledTasksPage.jsx"), "utf8");
const lobbyPage = readFileSync(join(here, "../pages/LobbyDisplayPage.jsx"), "utf8");
const notificationsPage = readFileSync(
  join(here, "../pages/settings/NotificationsSettingsPage.jsx"),
  "utf8",
);

describe("admin chrome — Live Channels type and buttons", () => {
  it("keeps wizard-note / panel leads at 14px, not a tighter --text-sm run-on", () => {
    assert.match(styles, /\.wizard-note[\s\S]{0,80}\.wizard-summary\s*\{[^}]*font-size:\s*14px/s);
    assert.match(styles, /\.config-panel-lead\s*\{[^}]*font-size:\s*14px/s);
    assert.match(styles, /\.status-secondary\s*\{[^}]*font-size:\s*14px/s);
    assert.match(styles, /\.settings-field-hint\s*\{[^}]*font-size:\s*14px/s);
  });

  it("does not stretch gold buttons in auto-fit field grids", () => {
    assert.match(styles, /\.service-fields > button[^{]*\{[^}]*align-self:\s*end/s);
    assert.match(styles, /\.service-card-actions\s*\{[^}]*gap:\s*12px/s);
  });

  it("wraps Overview / Connections card primaries in service-card-actions", () => {
    assert.match(configPage, /className="service-card-actions"/);
    assert.match(configPage, /className="btn-link" data-testid="live-overview-open"/);
    assert.match(configPage, /data-testid="verify-llm"/);
    assert.match(configPage, /className="primary"[\s\S]*?data-testid="library-sync-button"/);
  });

  it("uses one primary per region on Holidays, Tasks, Lobby, and member send slots", () => {
    assert.match(holidaysPage, /className="primary"[^>]*data-testid="holidays-add"/);
    assert.match(holidaysPage, /className="ghost"[\s\S]*?data-testid="holidays-restore-defaults"/);
    assert.match(tasksPage, /className="primary"[\s\S]*?data-testid="warm-explore-preset"/);
    assert.match(tasksPage, /className="primary"[\s\S]*?data-testid="task-detail-run-now"/);
    assert.match(lobbyPage, /className="btn-link"[\s\S]*?data-testid="lobby-open-kiosk"/);
    assert.match(lobbyPage, /className="ghost"[\s\S]*?data-testid="lobby-copy-url"/);
    assert.match(
      notificationsPage,
      /className="primary"[\s\S]*?data-testid="notifications-newsletter-self-send"/,
    );
    assert.match(
      notificationsPage,
      /className="primary"[\s\S]*?data-testid="notifications-yir-self-generate"/,
    );
  });
});

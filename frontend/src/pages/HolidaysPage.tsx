import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useConfirmModal } from "../hooks/useConfirmModal";
import { ShelfEditor } from "../components/live/SeasonalShelves";
import { holidaySummary, observanceListState } from "../lib/seasonalShelves";
import {
  createHoliday,
  deleteHoliday,
  getHolidayRail,
  listHolidays,
  restoreHolidayDefaults,
  updateHoliday,
} from "../api/client";
import SettingsPageHeader from "../components/settings/SettingsPageHeader";
import SettingsPanel from "../components/settings/SettingsPanel";
import SettingsToggle from "../components/settings/SettingsToggle";

const EMPTY_FORM = {
  name: "",
  kind: "fixed",
  month: 1,
  day: 1,
  movable_rule: "thanksgiving",
  pre_shoulder_days: 7,
  post_shoulder_days: 2,
  search_terms: "",
  enabled: true,
  schedule_publish: true,
};

function termsToInput(terms: any) {
  return Array.isArray(terms) ? terms.join(", ") : String(terms || "");
}

function inputToTerms(value: any) {
  return String(value || "")
    .split(/[\n,]+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function observanceToForm(item: any) {
  return {
    name: item.name || "",
    kind: item.kind || "fixed",
    month: item.month ?? 1,
    day: item.day ?? 1,
    movable_rule: item.movable_rule || "thanksgiving",
    pre_shoulder_days: item.pre_shoulder_days ?? 7,
    post_shoulder_days: item.post_shoulder_days ?? 2,
    search_terms: termsToInput(item.search_terms),
    enabled: item.enabled !== false,
    schedule_publish: item.schedule_publish !== false,
  };
}

export default function HolidaysPage() {
  const [items, setItems] = useState<any[]>([]);
  const [schedule, setSchedule] = useState<any[]>([]);
  const [selectedId, setSelectedId] = useState<any | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [creating, setCreating] = useState(false);
  const [rail, setRail] = useState<any | null>(null);
  const [status, setStatus] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState<"shelf" | "dates" | "live" | "matching">("shelf");

  const selected = useMemo(
    () => items.find((item) => item.id === selectedId) || null,
    [items, selectedId],
  );
  const { confirm, modal } = useConfirmModal();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listHolidays();
      setItems(data.items || []);
      setSchedule(data.schedule || []);
      setStatus(null);
    } catch (error: unknown) {
      setStatus({ type: "error", message: (error as { message?: string }).message || "Could not load holidays." });
    } finally {
      setLoading(false);
    }
  }, []);

  const loadRail = useCallback(async (observanceId: any) => {
    if (!observanceId) {
      setRail(null);
      return;
    }
    try {
      const data = await getHolidayRail(observanceId);
      setRail(data);
    } catch (error: unknown) {
      setRail(null);
      setStatus({ type: "error", message: (error as { message?: string }).message || "Could not load rail titles." });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (selected) {
      setCreating(false);
      setForm(observanceToForm(selected));
      loadRail(selected.id);
    }
  }, [selected, loadRail]);

  function patchForm(patch: any) {
    setForm((prev) => ({ ...prev, ...patch }));
  }

  function startCreate() {
    setCreating(true);
    setSelectedId(null);
    setForm(EMPTY_FORM);
    setRail(null);
  }

  async function handleSave(event: any) {
    event.preventDefault();
    setSaving(true);
    setStatus(null);
    const payload = {
      name: form.name.trim(),
      kind: form.kind,
      month: form.kind === "fixed" ? Number(form.month) : null,
      day: form.kind === "fixed" ? Number(form.day) : null,
      movable_rule: form.kind === "movable" ? form.movable_rule : null,
      pre_shoulder_days: Number(form.pre_shoulder_days) || 0,
      post_shoulder_days: Number(form.post_shoulder_days) || 0,
      search_terms: inputToTerms(form.search_terms),
      enabled: Boolean(form.enabled),
      schedule_publish: Boolean(form.schedule_publish),
    };
    try {
      if (creating || !selectedId) {
        const result = await createHoliday(payload);
        const id = result.item?.id;
        await load();
        if (id) setSelectedId(id);
        setCreating(false);
        setStatus({ type: "success", message: "Holiday added to the household calendar." });
      } else {
        await updateHoliday(selectedId, payload);
        await load();
        await loadRail(selectedId);
        setStatus({ type: "success", message: "Holiday saved." });
      }
    } catch (error: unknown) {
      setStatus({ type: "error", message: (error as { message?: string }).message || "Could not save holiday." });
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!selectedId || creating) return;
    if (
      !(await confirm({
        title: "Remove holiday",
        body: `Remove “${selected?.name || "this holiday"}” from the calendar?`,
        confirmLabel: "Remove",
        danger: true,
      }))
    ) {
      return;
    }
    try {
      await deleteHoliday(selectedId);
      setSelectedId(null);
      setRail(null);
      await load();
      setStatus({ type: "success", message: "Holiday removed. Restore defaults can bring built-ins back." });
    } catch (error: unknown) {
      setStatus({ type: "error", message: (error as { message?: string }).message || "Could not delete." });
    }
  }

  async function handleRestore() {
    if (
      !(await confirm({
        title: "Restore built-in holidays",
        body: "Restore built-in holidays to their default shoulders and filter terms? Family customs stay.",
        confirmLabel: "Restore defaults",
      }))
    ) {
      return;
    }
    try {
      const data = await restoreHolidayDefaults();
      setItems(data.items || []);
      setStatus({ type: "success", message: "Built-in holidays restored." });
      if (selectedId) await loadRail(selectedId);
    } catch (error: unknown) {
      setStatus({ type: "error", message: (error as { message?: string }).message || "Could not restore defaults." });
    }
  }

  const showDates = creating || tab === "dates";
  const showMatching = creating || tab === "matching";
  const showLive = creating || tab === "live";
  const showShelf = !creating && Boolean(selected) && tab === "shelf";
  const shelfCount = Array.isArray(rail?.items) ? rail.items.length : 0;

  if (loading) {
    return (
      <div className="settings-stack" data-testid="admin-holidays">
        <SettingsPageHeader title="Holidays">Loading the household calendar…</SettingsPageHeader>
        {modal}
      </div>
    );
  }

  return (
    <div className="settings-stack holidays-page" data-testid="admin-holidays">
        <SettingsPageHeader title="Holidays & seasons">
        One place for the observances Explore shelves are built around: the theme, the picks, the
        dates, and whether Live carries the block.
      </SettingsPageHeader>

      {status ? (
        <p
          className={`status ${status.type === "error" ? "status-error" : "status-success"}`}
          data-testid="holidays-status"
        >
          {status.message}
        </p>
      ) : null}

      <div className="holidays-layout">
        <SettingsPanel
          title="Observances"
          lead="Enable or disable without deleting. Family customs live alongside the built-in set."
          testId="holidays-list-panel"
          footer={
            <div className="settings-actions">
              <button type="button" className="primary" onClick={startCreate} data-testid="holidays-add">
                Add your own
              </button>
              <button
                type="button"
                className="ghost"
                onClick={handleRestore}
                data-testid="holidays-restore-defaults"
              >
                Restore defaults
              </button>
            </div>
          }
        >
          <ul className="holidays-list" data-testid="holidays-list">
            {items.map((item) => {
              const active = !creating && item.id === selectedId;
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    className={`holidays-list-item ${active ? "is-active" : ""} ${
                      item.enabled ? "" : "is-disabled"
                    }`}
                    data-testid={`holiday-row-${item.id}`}
                    onClick={() => {
                      setCreating(false);
                      setSelectedId(item.id);
                    }}
                  >
                    <strong>{item.name}</strong>
                    <span className="muted">
                      {observanceListState(item, schedule)}
                      {" · "}
                      {item.grounding_date_label || item.grounding_date || "—"}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </SettingsPanel>

        <form onSubmit={handleSave} className="holidays-editor">
          <SettingsPanel
            title={creating ? "New holiday" : selected ? selected.name : "Edit holiday"}
            lead={
              creating
                ? "Grounding date is the day the holiday is pinned to. Shoulders can differ."
                : "On or off for Explore. The tabs are the shelf, the dates, Live, and the words that match."
            }
            testId="holidays-editor-panel"
          >
            {!creating && !selected ? (
              <p className="muted">Pick an observance on the left, or add a family day.</p>
            ) : (
              <>
                {!creating && selected ? (
                  <>
                    <p data-testid="holiday-summary">
                      {holidaySummary({ item: selected, schedule, shelfCount })}
                    </p>
                    <div className="holiday-tabs" role="tablist" aria-label="Holiday sections">
                      {(
                        [
                          ["shelf", "The shelf"],
                          ["dates", "Dates"],
                          ["live", "On Live"],
                          ["matching", "Matching"],
                        ] as const
                      ).map(([id, label]) => (
                        <button
                          key={id}
                          type="button"
                          role="tab"
                          aria-selected={tab === id}
                          className={tab === id ? "ghost is-active" : "ghost"}
                          data-testid={`holiday-tab-${id}`}
                          onClick={() => setTab(id)}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </>
                ) : null}
                {showShelf && selected ? (
                  <div data-testid="holidays-rail-panel">
                    <ShelfEditor
                      item={selected}
                      onSaved={() => {
                        void load();
                      }}
                    />
                  </div>
                ) : null}
                {showDates ? (
                <>
                <label className="settings-field">
                  <span>Name</span>
                  <input
                    type="text"
                    value={form.name}
                    onChange={(e) => patchForm({ name: e.target.value })}
                    required
                    data-testid="holiday-name"
                  />
                </label>

                <label className="settings-field">
                  <span>Kind</span>
                  <select
                    value={form.kind}
                    onChange={(e) => patchForm({ kind: e.target.value })}
                    data-testid="holiday-kind"
                  >
                    <option value="fixed">Fixed month/day</option>
                    <option value="movable">Movable (US rules)</option>
                  </select>
                </label>

                {form.kind === "fixed" ? (
                  <div className="settings-field-grid">
                    <label className="settings-field">
                      <span>Month</span>
                      <input
                        type="number"
                        min={1}
                        max={12}
                        value={form.month}
                        onChange={(e) => patchForm({ month: Number(e.target.value) })}
                        data-testid="holiday-month"
                      />
                    </label>
                    <label className="settings-field">
                      <span>Day</span>
                      <input
                        type="number"
                        min={1}
                        max={31}
                        value={form.day}
                        onChange={(e) => patchForm({ day: Number(e.target.value) })}
                        data-testid="holiday-day"
                      />
                    </label>
                  </div>
                ) : (
                  <label className="settings-field">
                    <span>Movable rule</span>
                    <select
                      value={form.movable_rule}
                      onChange={(e) => patchForm({ movable_rule: e.target.value })}
                      data-testid="holiday-movable-rule"
                    >
                      <option value="thanksgiving">Thanksgiving (4th Thursday in November)</option>
                      <option value="labor_day">Labor Day (1st Monday in September)</option>
                      <option value="arbor_day">Arbor Day (last Friday in April)</option>
                    </select>
                  </label>
                )}

                {!creating && selected?.grounding_date_label ? (
                  <p className="holidays-grounding" data-testid="holiday-grounding">
                    Grounding date: <strong>{selected.grounding_date_label}</strong>
                  </p>
                ) : null}

                <div className="settings-field-grid">
                  <label className="settings-field">
                    <span>Days before</span>
                    <input
                      type="number"
                      min={0}
                      max={90}
                      value={form.pre_shoulder_days}
                      onChange={(e) => patchForm({ pre_shoulder_days: Number(e.target.value) })}
                      data-testid="holiday-pre-shoulder"
                    />
                  </label>
                  <label className="settings-field">
                    <span>Days after</span>
                    <input
                      type="number"
                      min={0}
                      max={90}
                      value={form.post_shoulder_days}
                      onChange={(e) => patchForm({ post_shoulder_days: Number(e.target.value) })}
                      data-testid="holiday-post-shoulder"
                    />
                  </label>
                </div>
                </>
                ) : null}
                {showMatching ? (
                <label className="settings-field">
                  <span>Keyword terms</span>
                  <textarea
                    rows={3}
                    value={form.search_terms}
                    onChange={(e) => patchForm({ search_terms: e.target.value })}
                    placeholder="christmas, santa claus, nutcracker"
                    data-testid="holiday-search-terms"
                  />
                  <span className="settings-field-hint">
                    Specific words count on their own. Broad words such as winter or family only
                    count when a keyword or the plot already matches the holiday.
                  </span>
                </label>
                ) : null}

                <SettingsToggle
                  id="holiday-enabled"
                  checked={Boolean(form.enabled)}
                  onChange={(v) => patchForm({ enabled: v })}
                  label="Enabled for Explore seasonal rail"
                  help="Disabled holidays stay on the list but never drive the rail."
                  testId="holiday-enabled-toggle"
                />
                {showLive ? (
                <>
                <SettingsToggle
                  id="holiday-schedule"
                  checked={Boolean(form.schedule_publish)}
                  onChange={(v) => patchForm({ schedule_publish: v })}
                  label="Include in scheduled seasonal rails"
                  help="When on, the daily seasonal rail task may publish this window to Explore."
                  testId="holiday-schedule-toggle"
                />
                <p className="settings-field-hint">
                  When the Live block is on, this window can publish on the seasonal rail. Channel
                  settings stay on{" "}
                  <Link to="/admin/live-channels" data-testid="holiday-live-link">
                    Live
                  </Link>
                  .
                </p>
                </>
                ) : null}

                {creating || tab !== "shelf" ? (
                <div className="settings-actions">
                  <button type="submit" disabled={saving} data-testid="holiday-save">
                    {saving ? "Saving…" : creating ? "Create holiday" : "Save changes"}
                  </button>
                  {!creating && selected ? (
                    <button
                      type="button"
                      className="ghost"
                      onClick={handleDelete}
                      data-testid="holiday-delete"
                    >
                      Delete
                    </button>
                  ) : null}
                </div>
                ) : null}
              </>
            )}
          </SettingsPanel>
        </form>
      </div>


      <SettingsPanel
        title="Upcoming scheduled rails"
        lead="Windows from the calendar that can publish to Explore’s seasonal shelf."
        testId="holidays-schedule-panel"
      >
        {schedule.length ? (
          <ul className="holidays-schedule" data-testid="holidays-schedule">
            {schedule.slice(0, 12).map((row) => (
              <li key={`${row.id}-${row.grounding_date}`}>
                <strong>{row.name}</strong>
                <span className="muted">
                  {" "}
                  · grounded {row.grounding_date} · {row.window_start} → {row.window_end}
                  {row.active_now ? " · active now" : ""}
                  {!row.schedule_publish ? " · schedule off" : ""}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No upcoming windows in the next couple of months.</p>
        )}
      </SettingsPanel>
      {modal}
    </div>
  );
}

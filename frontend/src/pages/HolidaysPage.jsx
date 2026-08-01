import { useCallback, useEffect, useMemo, useState } from "react";
import {
  clearHolidayRailTitle,
  createHoliday,
  deleteHoliday,
  getHolidayRail,
  listHolidays,
  restoreHolidayDefaults,
  searchHolidayLibrary,
  setHolidayRailTitle,
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

function termsToInput(terms) {
  return Array.isArray(terms) ? terms.join(", ") : String(terms || "");
}

function inputToTerms(value) {
  return String(value || "")
    .split(/[\n,]+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function observanceToForm(item) {
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
  const [items, setItems] = useState([]);
  const [schedule, setSchedule] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [creating, setCreating] = useState(false);
  const [rail, setRail] = useState(null);
  const [libraryQuery, setLibraryQuery] = useState("");
  const [libraryHits, setLibraryHits] = useState([]);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const selected = useMemo(
    () => items.find((item) => item.id === selectedId) || null,
    [items, selectedId],
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listHolidays();
      setItems(data.items || []);
      setSchedule(data.schedule || []);
      setStatus(null);
    } catch (error) {
      setStatus({ type: "error", message: error.message || "Could not load holidays." });
    } finally {
      setLoading(false);
    }
  }, []);

  const loadRail = useCallback(async (observanceId) => {
    if (!observanceId) {
      setRail(null);
      return;
    }
    try {
      const data = await getHolidayRail(observanceId);
      setRail(data);
    } catch (error) {
      setRail(null);
      setStatus({ type: "error", message: error.message || "Could not load rail titles." });
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

  function patchForm(patch) {
    setForm((prev) => ({ ...prev, ...patch }));
  }

  function startCreate() {
    setCreating(true);
    setSelectedId(null);
    setForm(EMPTY_FORM);
    setRail(null);
  }

  async function handleSave(event) {
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
    } catch (error) {
      setStatus({ type: "error", message: error.message || "Could not save holiday." });
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!selectedId || creating) return;
    if (!window.confirm(`Remove “${selected?.name || "this holiday"}” from the calendar?`)) return;
    try {
      await deleteHoliday(selectedId);
      setSelectedId(null);
      setRail(null);
      await load();
      setStatus({ type: "success", message: "Holiday removed. Restore defaults can bring built-ins back." });
    } catch (error) {
      setStatus({ type: "error", message: error.message || "Could not delete." });
    }
  }

  async function handleRestore() {
    if (!window.confirm("Restore built-in holidays to their default shoulders and filter terms? Family customs stay.")) {
      return;
    }
    try {
      const data = await restoreHolidayDefaults();
      setItems(data.items || []);
      setStatus({ type: "success", message: "Built-in holidays restored." });
      if (selectedId) await loadRail(selectedId);
    } catch (error) {
      setStatus({ type: "error", message: error.message || "Could not restore defaults." });
    }
  }

  async function handleLibrarySearch(event) {
    event.preventDefault();
    try {
      const data = await searchHolidayLibrary(libraryQuery.trim());
      setLibraryHits(data.items || []);
    } catch (error) {
      setStatus({ type: "error", message: error.message || "Library search failed." });
    }
  }

  async function applyCuration(libraryItemId, curation) {
    if (!selectedId) return;
    try {
      const data = await setHolidayRailTitle(selectedId, {
        library_item_id: libraryItemId,
        curation,
      });
      setRail((prev) => ({ ...(prev || {}), curation: data.curation || [] }));
      await loadRail(selectedId);
      setStatus({
        type: "success",
        message:
          curation === "exclude"
            ? "Hidden from this rail."
            : curation === "include"
              ? "Always included on this rail."
              : "Pinned to the front of this rail.",
      });
    } catch (error) {
      setStatus({ type: "error", message: error.message || "Could not update rail title." });
    }
  }

  async function removeCuration(libraryItemId) {
    if (!selectedId) return;
    try {
      await clearHolidayRailTitle(selectedId, libraryItemId);
      await loadRail(selectedId);
    } catch (error) {
      setStatus({ type: "error", message: error.message || "Could not clear curation." });
    }
  }

  if (loading) {
    return (
      <div className="settings-stack" data-testid="admin-holidays">
        <SettingsPageHeader title="Holidays">Loading the household calendar…</SettingsPageHeader>
      </div>
    );
  }

  return (
    <div className="settings-stack holidays-page" data-testid="admin-holidays">
      <SettingsPageHeader title="Holidays">
        Tune the household calendar that drives Explore’s seasonal rail — grounding day, how long
        before and after it should linger, and which titles belong on the shelf.
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
              <button type="button" className="ghost" onClick={startCreate} data-testid="holidays-add">
                Add holiday
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
                      {item.grounding_date_label || item.grounding_date || "—"}
                      {" · "}
                      {item.pre_shoulder_days}d before / {item.post_shoulder_days}d after
                      {!item.enabled ? " · off" : ""}
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
            lead="Grounding date is the day the holiday is pinned to. Shoulders can differ."
            testId="holidays-editor-panel"
          >
            {!creating && !selected ? (
              <p className="muted">Select a holiday or add a family day.</p>
            ) : (
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

                <label className="settings-field">
                  <span>Search / filter terms</span>
                  <textarea
                    rows={3}
                    value={form.search_terms}
                    onChange={(e) => patchForm({ search_terms: e.target.value })}
                    placeholder="christmas, holiday, winter, family"
                    data-testid="holiday-search-terms"
                  />
                </label>

                <SettingsToggle
                  id="holiday-enabled"
                  checked={Boolean(form.enabled)}
                  onChange={(v) => patchForm({ enabled: v })}
                  label="Enabled for Explore seasonal rail"
                  help="Disabled holidays stay on the list but never drive the rail."
                  testId="holiday-enabled-toggle"
                />
                <SettingsToggle
                  id="holiday-schedule"
                  checked={Boolean(form.schedule_publish)}
                  onChange={(v) => patchForm({ schedule_publish: v })}
                  label="Include in scheduled seasonal rails"
                  help="When on, the daily seasonal rail task may publish this window to Explore."
                  testId="holiday-schedule-toggle"
                />

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
              </>
            )}
          </SettingsPanel>
        </form>
      </div>

      {selected && !creating ? (
        <SettingsPanel
          title="Rail titles"
          lead="Not a fit hides a bad match. Always include adds a favorite. Show first pins the head of the rail."
          testId="holidays-rail-panel"
        >
          {rail?.note ? <p className="muted">{rail.note}</p> : null}
          <div className="holidays-rail-preview" data-testid="holiday-rail-preview">
            <h4 className="settings-subsection-title">
              Preview · {rail?.label || selected.name}
              {rail?.grounding_date ? ` · grounded ${rail.grounding_date}` : ""}
            </h4>
            {(rail?.items || []).length ? (
              <ol className="holidays-rail-items">
                {rail.items.map((item) => (
                  <li key={item.id}>
                    <span>
                      {item.title}
                      {item.year ? ` (${item.year})` : ""}
                      {item.rail_role ? ` · ${item.rail_role}` : ""}
                    </span>
                    <span className="holidays-rail-actions">
                      <button
                        type="button"
                        className="ghost"
                        onClick={() => applyCuration(item.id, "pin")}
                        data-testid={`rail-pin-${item.id}`}
                      >
                        Show first
                      </button>
                      <button
                        type="button"
                        className="ghost"
                        onClick={() => applyCuration(item.id, "exclude")}
                        data-testid={`rail-exclude-${item.id}`}
                      >
                        Not a fit
                      </button>
                    </span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="muted">No titles on this rail yet.</p>
            )}
          </div>

          <div className="settings-subsection" data-testid="holiday-curation-list">
            <h4 className="settings-subsection-title">Saved curation</h4>
            {(rail?.curation || []).length ? (
              <ul>
                {(rail.curation || []).map((entry) => (
                  <li key={`${entry.curation}-${entry.library_item_id}`}>
                    <strong>{entry.title || `#${entry.library_item_id}`}</strong>
                    {" · "}
                    {entry.curation}
                    <button
                      type="button"
                      className="ghost"
                      onClick={() => removeCuration(entry.library_item_id)}
                      data-testid={`rail-clear-${entry.library_item_id}`}
                    >
                      Clear
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">No pins, includes, or excludes yet.</p>
            )}
          </div>

          <form onSubmit={handleLibrarySearch} className="holidays-library-search">
            <label className="settings-field">
              <span>Search library to add</span>
              <input
                type="search"
                value={libraryQuery}
                onChange={(e) => setLibraryQuery(e.target.value)}
                placeholder="Title in your collection"
                data-testid="holiday-library-search"
              />
            </label>
            <button type="submit" className="ghost" data-testid="holiday-library-search-submit">
              Search
            </button>
          </form>
          {libraryHits.length ? (
            <ul className="holidays-library-hits" data-testid="holiday-library-hits">
              {libraryHits.map((hit) => (
                <li key={hit.id}>
                  <span>
                    {hit.title}
                    {hit.year ? ` (${hit.year})` : ""}
                  </span>
                  <span className="holidays-rail-actions">
                    <button type="button" className="ghost" onClick={() => applyCuration(hit.id, "include")}>
                      Always include
                    </button>
                    <button type="button" className="ghost" onClick={() => applyCuration(hit.id, "pin")}>
                      Show first
                    </button>
                    <button type="button" className="ghost" onClick={() => applyCuration(hit.id, "exclude")}>
                      Not a fit
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </SettingsPanel>
      ) : null}

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
    </div>
  );
}

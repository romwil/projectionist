import { useCallback, useEffect, useState } from "react";
import {
  clearHolidayRailTitle,
  getHolidayRail,
  listHolidays,
  searchHolidayLibrary,
  setHolidayRailOrder,
  setHolidayRailTitle,
  updateHoliday,
} from "../../api/client";
import {
  addShelfIdFirst,
  moveShelfId,
  shelfDateLabel,
  shelfFormFromItem,
  shelfPatchFromForm,
  shelfRoleLabel,
} from "../../lib/seasonalShelves.js";

/**
 * Seasonal shelves — edit what Explore shows around each holiday, right where
 * the owner sets up Live. Same store as Admin → Holidays (no second shelf
 * system): titles come from the owner's own library, order and picks persist
 * as shelf curation, and the shelf name / date / window live on the holiday.
 */
function ShelfEditor({ item, onSaved }) {
  const [rail, setRail] = useState(null);
  const [form, setForm] = useState(() => shelfFormFromItem(item));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState(null);

  const loadRail = useCallback(async () => {
    try {
      setRail(await getHolidayRail(item.id));
    } catch (error) {
      setMessage({ type: "error", text: error?.message || "Could not load this shelf." });
    }
  }, [item.id]);

  useEffect(() => {
    loadRail();
  }, [loadRail]);

  const titles = rail?.items || [];
  const ids = titles.map((row) => Number(row.id));

  async function run(task, success) {
    setBusy(true);
    setMessage(null);
    try {
      await task();
      if (success) setMessage({ type: "success", text: success });
    } catch (error) {
      setMessage({ type: "error", text: error?.message || "That didn’t save." });
    } finally {
      setBusy(false);
    }
  }

  const saveOrder = (nextIds) =>
    run(async () => {
      const result = await setHolidayRailOrder(item.id, nextIds);
      if (result?.preview) setRail(result.preview);
    }, "Shelf order saved.");

  return (
    <div className="live-shelf-editor" data-testid={`live-shelf-editor-${item.id}`}>
      <p className="live-studio-hint">
        {rail?.note ||
          "These are the titles Explore shows for this season. Reorder them, drop a bad fit, or add your own."}
      </p>
      {titles.length ? (
        <ol className="live-shelf-titles" data-testid={`live-shelf-titles-${item.id}`}>
          {titles.map((row, index) => (
            <li key={row.id} data-testid={`live-shelf-title-${item.id}-${row.id}`}>
              <span className="live-shelf-title-name">
                {row.title}
                {row.year ? ` (${row.year})` : ""}
              </span>
              <span className="live-shelf-title-role">{shelfRoleLabel(row.rail_role)}</span>
              <span className="live-shelf-title-actions">
                <button
                  type="button"
                  className="ghost"
                  aria-label={`Move ${row.title} up`}
                  disabled={busy || index === 0}
                  data-testid={`live-shelf-up-${item.id}-${row.id}`}
                  onClick={() => saveOrder(moveShelfId(ids, index, -1))}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="ghost"
                  aria-label={`Move ${row.title} down`}
                  disabled={busy || index === titles.length - 1}
                  data-testid={`live-shelf-down-${item.id}-${row.id}`}
                  onClick={() => saveOrder(moveShelfId(ids, index, 1))}
                >
                  ↓
                </button>
                <button
                  type="button"
                  className="ghost"
                  disabled={busy}
                  data-testid={`live-shelf-remove-${item.id}-${row.id}`}
                  onClick={() =>
                    run(async () => {
                      await setHolidayRailTitle(item.id, {
                        library_item_id: Number(row.id),
                        curation: "exclude",
                      });
                      await loadRail();
                    }, `${row.title} is off this shelf.`)
                  }
                >
                  Not a fit
                </button>
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="live-studio-hint" data-testid={`live-shelf-empty-${item.id}`}>
          Nothing in your library matches this season yet. Add a title below, or widen the
          keywords.
        </p>
      )}

      <form
        className="live-shelf-add"
        onSubmit={async (event) => {
          event.preventDefault();
          if (!query.trim()) return;
          await run(async () => {
            const result = await searchHolidayLibrary(query.trim(), { limit: 8 });
            setHits(result?.items || []);
          });
        }}
      >
        <label>
          <span>Add a title from your library</span>
          <input
            type="search"
            value={query}
            placeholder="Search your library"
            data-testid={`live-shelf-search-${item.id}`}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <button type="submit" className="ghost" disabled={busy || !query.trim()}>
          Search
        </button>
      </form>
      {hits ? (
        <ul className="live-shelf-hits">
          {hits.length === 0 ? <li className="live-studio-hint">No matches in your library.</li> : null}
          {hits.map((hit) => (
            <li key={hit.id}>
              <span>
                {hit.title}
                {hit.year ? ` (${hit.year})` : ""}
              </span>
              <button
                type="button"
                className="ghost"
                disabled={busy}
                data-testid={`live-shelf-add-${item.id}-${hit.id}`}
                onClick={() =>
                  saveOrder(addShelfIdFirst(ids, hit.id)).then(() => {
                    setHits(null);
                    setQuery("");
                  })
                }
              >
                Add to the front
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <details className="live-shelf-details">
        <summary>Name, date &amp; window</summary>
        <div className="live-shelf-form">
          <label>
            <span>Shelf name</span>
            <input
              type="text"
              value={form.name}
              data-testid={`live-shelf-name-${item.id}`}
              onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
            />
          </label>
          {item.kind === "movable" ? (
            <p className="live-studio-hint">Date: {shelfDateLabel(item)} (moves each year).</p>
          ) : (
            <div className="live-shelf-date">
              <label>
                <span>Month</span>
                <input
                  type="number"
                  min={1}
                  max={12}
                  value={form.month}
                  onChange={(event) => setForm((prev) => ({ ...prev, month: event.target.value }))}
                />
              </label>
              <label>
                <span>Day</span>
                <input
                  type="number"
                  min={1}
                  max={31}
                  value={form.day}
                  onChange={(event) => setForm((prev) => ({ ...prev, day: event.target.value }))}
                />
              </label>
            </div>
          )}
          <div className="live-shelf-date">
            <label>
              <span>Days before</span>
              <input
                type="number"
                min={0}
                max={90}
                value={form.pre_shoulder_days}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, pre_shoulder_days: event.target.value }))
                }
              />
            </label>
            <label>
              <span>Days after</span>
              <input
                type="number"
                min={0}
                max={90}
                value={form.post_shoulder_days}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, post_shoulder_days: event.target.value }))
                }
              />
            </label>
          </div>
          <label>
            <span>Keywords that match this season</span>
            <input
              type="text"
              value={form.search_terms}
              placeholder="horror, haunted, witch"
              onChange={(event) =>
                setForm((prev) => ({ ...prev, search_terms: event.target.value }))
              }
            />
          </label>
          <label className="live-studio-check">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(event) => setForm((prev) => ({ ...prev, enabled: event.target.checked }))}
            />
            <span>Show this shelf in Explore when its season comes round</span>
          </label>
          <button
            type="button"
            className="primary"
            disabled={busy || !form.name.trim()}
            data-testid={`live-shelf-save-${item.id}`}
            onClick={() =>
              run(async () => {
                const saved = await updateHoliday(item.id, shelfPatchFromForm(form, item));
                onSaved?.(saved?.item || null);
                await loadRail();
              }, "Shelf saved.")
            }
          >
            Save shelf
          </button>
        </div>
      </details>
      {message ? (
        <p
          className={`live-studio-note live-studio-note--${message.type}`}
          role={message.type === "error" ? "alert" : "status"}
          data-testid={`live-shelf-message-${item.id}`}
        >
          {message.text}
        </p>
      ) : null}
    </div>
  );
}

export default function SeasonalShelves() {
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");
  const [openId, setOpenId] = useState("");

  useEffect(() => {
    let cancelled = false;
    listHolidays()
      .then((data) => {
        if (!cancelled) setItems(data?.items || []);
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || "Could not load seasonal shelves.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="live-studio-card live-shelves" data-testid="live-seasonal-shelves">
      <header className="live-studio-card-head">
        <div>
          <h3>Seasonal shelves</h3>
          <p className="live-studio-hint">
            Titles from your library, grouped by season. They show up on Explore around each
            holiday. Reorder them, drop a bad fit, or rename a shelf.
          </p>
        </div>
      </header>
      {error ? (
        <p className="live-studio-note live-studio-note--error" role="alert">
          {error}
        </p>
      ) : null}
      {items === null && !error ? <p className="live-studio-hint">Loading shelves…</p> : null}
      {items && items.length === 0 ? (
        <p className="live-studio-hint" data-testid="live-shelves-empty">
          No seasonal shelves yet. Add holidays under Admin → Holidays and they’ll appear here.
        </p>
      ) : null}
      <ul className="live-shelf-list">
        {(items || []).map((item) => {
          const open = openId === item.id;
          return (
            <li key={item.id} className="live-shelf" data-testid={`live-shelf-${item.id}`}>
              <button
                type="button"
                className="live-shelf-head"
                aria-expanded={open}
                data-testid={`live-shelf-toggle-${item.id}`}
                onClick={() => setOpenId(open ? "" : item.id)}
              >
                <span className="live-shelf-name">{item.name}</span>
                <span className="live-shelf-date-label">{shelfDateLabel(item)}</span>
                <span className={item.enabled === false ? "live-shelf-pill" : "live-shelf-pill is-on"}>
                  {item.enabled === false ? "Off" : "On"}
                </span>
              </button>
              {open ? (
                <ShelfEditor
                  item={item}
                  onSaved={(saved) =>
                    saved &&
                    setItems((prev) => (prev || []).map((row) => (row.id === saved.id ? saved : row)))
                  }
                />
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

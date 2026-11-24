import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  applyHolidayRailCuration,
  getHolidayRail,
  proposeHolidayRailCuration,
  searchHolidayLibrary,
  setHolidayRailCuratorNote,
  setHolidayRailMix,
  setHolidayRailOrder,
  setHolidayRailTitle,
  updateHoliday,
} from "../../api/client";
import {
  DEFAULT_ROLE_MIX,
  SHELF_PICK_ROLES,
  addShelfIdFirst,
  curateClickPlan,
  moveShelfId,
  shelfDateLabel,
  shelfFormFromItem,
  shelfPatchFromForm,
  shelfPickRole,
  shelfRoleLabel,
  visibleCuratedShelf,
} from "../../lib/seasonalShelves.js";
import SeasonalPickChatPane from "../SeasonalPickChatPane";

type ShelfItem = {
  id: number | string;
  name?: string;
  kind?: string;
  enabled?: boolean;
  month?: number;
  day?: number;
  pre_shoulder_days?: number;
  post_shoulder_days?: number;
  search_terms?: unknown;
};

type ShelfTitle = {
  id: number | string;
  title?: string;
  year?: number | string;
  curator_note?: string;
  why?: string;
  rail_role?: string;
  shelf_role?: string;
  role?: string;
  matched_because?: string;
};

type ShelfProposal = {
  theme: string;
  picks: Array<Record<string, unknown>>;
  applyPicks: Array<Record<string, unknown>>;
};

type ShelfRail = {
  items?: ShelfTitle[];
  replaces_matches?: boolean;
  note?: string;
  theme?: string;
  role_mix?: Record<string, number>;
};

type ShelfForm = {
  name: string;
  month: number | string;
  day: number | string;
  pre_shoulder_days: number | string;
  post_shoulder_days: number | string;
  search_terms: string;
  enabled: boolean;
};

type ShelfMessage = { type: "error" | "success"; text: string };

type LibraryHit = {
  id: number | string;
  title?: string;
  year?: number | string;
};

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) return err.message;
  if (typeof err === "object" && err && "message" in err) {
    const message = (err as { message: unknown }).message;
    if (typeof message === "string" && message) return message;
  }
  return fallback;
}

/**
 * Seasonal shelves — edit what Explore shows around each holiday, right where
 * the owner sets up Live. Same store as Admin → Holidays (no second shelf
 * system): titles come from the owner's own library, order and picks persist
 * as shelf curation, and the shelf name / date / window live on the holiday.
 */
export function ShelfEditor({
  item,
  onSaved,
  showCalendar = false,
}: {
  item: ShelfItem;
  onSaved?: (saved: ShelfItem | null) => void;
  showCalendar?: boolean;
}) {
  const [rail, setRail] = useState<ShelfRail | null>(null);
  const [form, setForm] = useState<ShelfForm>(() => shelfFormFromItem(item) as ShelfForm);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<ShelfMessage | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<LibraryHit[] | null>(null);
  const [noteDrafts, setNoteDrafts] = useState<Record<number, string>>({});
  const [chatTitle, setChatTitle] = useState<ShelfTitle | null>(null);
  const [curateBusy, setCurateBusy] = useState(false);
  const [proposal, setProposal] = useState<ShelfProposal | null>(null);
  const [mix, setMix] = useState<Record<string, number>>(DEFAULT_ROLE_MIX);
  const [dragIndex, setDragIndex] = useState<number | null>(null);

  const loadRail = useCallback(async () => {
    try {
      const next = (await getHolidayRail(item.id)) as ShelfRail;
      setRail(next);
      if (next?.role_mix && Object.keys(next.role_mix).length) {
        setMix({ ...DEFAULT_ROLE_MIX, ...next.role_mix });
      }
    } catch (error: unknown) {
      setMessage({ type: "error", text: errorMessage(error, "Could not load this shelf.") });
    }
  }, [item.id]);

  useEffect(() => {
    loadRail();
  }, [loadRail]);

  const titles = visibleCuratedShelf(rail?.items, {
    replacesMatches: Boolean(rail?.replaces_matches),
  }) as ShelfTitle[];
  const ids = titles.map((row) => Number(row.id));
  const chatOpen = Boolean(chatTitle);

  async function run(task: () => Promise<void>, success?: string) {
    setBusy(true);
    setMessage(null);
    try {
      await task();
      if (success) setMessage({ type: "success", text: success });
    } catch (error: unknown) {
      setMessage({ type: "error", text: errorMessage(error, "That didn’t save.") });
    } finally {
      setBusy(false);
    }
  }

  const saveOrder = (nextIds: number[]) =>
    run(async () => {
      const result = (await setHolidayRailOrder(item.id, nextIds)) as { preview?: ShelfRail };
      if (result?.preview) setRail(result.preview);
    }, "Shelf order saved.");

  function noteFor(row: ShelfTitle) {
    const id = Number(row.id);
    if (Object.prototype.hasOwnProperty.call(noteDrafts, id)) return noteDrafts[id];
    return String(row.curator_note || row.why || "");
  }

  return (
    <div
      className={`live-shelf-editor${chatOpen ? " live-shelf-editor--chat-open" : ""}`}
      data-testid={`live-shelf-editor-${item.id}`}
    >
      <div className="live-shelf-editor-main">
        {rail?.theme ? (
          <p className="live-shelf-theme" data-testid={`live-shelf-theme-${item.id}`}>
            {item.name} — {rail.theme}
          </p>
        ) : null}
        <p className="live-studio-hint">
          {rail?.note ||
            "Household members see these picks on Explore with staff-pick notes. Ask the professor for a theme and a mix, then apply it. Nothing changes until you do."}
        </p>

        <fieldset className="live-shelf-mix" data-testid={`live-shelf-mix-${item.id}`}>
          <legend>Mix</legend>
          {SHELF_PICK_ROLES.map((role) => {
            const inputId = `live-shelf-mix-${item.id}-${role.replace(/\s+/g, "-").toLowerCase()}`;
            return (
            <label key={role} htmlFor={inputId}>
              <span>{role}</span>
              <input
                id={inputId}
                type="number"
                min={0}
                max={16}
                value={mix[role] ?? 0}
                disabled={busy}
                aria-label={`${role} picks`}
                onChange={(event) =>
                  setMix((prev) => ({ ...prev, [role]: Math.max(0, Number(event.target.value) || 0) }))
                }
              />
            </label>
            );
          })}
        </fieldset>

        <div className="live-shelf-curate-bar">
          <button
            type="button"
            className="primary"
            disabled={busy}
            aria-busy={curateBusy}
            data-testid={`live-shelf-curate-${item.id}`}
            onClick={() => {
              setCurateBusy(true);
              void run(async () => {
                try {
                  await setHolidayRailMix(item.id, mix);
                  const result = (await proposeHolidayRailCuration(item.id, {
                    limit: 10,
                    role_mix: mix,
                  })) as { picks?: unknown[]; theme?: string };
                  const plan = curateClickPlan({ proposal: result });
                  if (!plan.ok) throw new Error(plan.message);
                  setProposal({
                    theme: plan.theme,
                    picks: (result.picks || []) as Array<Record<string, unknown>>,
                    applyPicks: plan.applyPicks as Array<Record<string, unknown>>,
                  });
                } finally {
                  setCurateBusy(false);
                }
              });
            }}
          >
            {curateBusy ? "Asking the professor…" : proposal ? "Ask the curator to redo" : "Ask the professor to curate"}
          </button>
        </div>
        {proposal ? (
          <div className="live-shelf-proposal" data-testid={`live-shelf-proposal-${item.id}`}>
            <p>
              <strong>{proposal.theme || "A new shelf"}</strong>
            </p>
            <ol className="live-shelf-proposal-list">
              {proposal.picks.map((pick) => (
                <li key={String(pick.library_item_id || pick.id)}>
                  <span>
                    {String(pick.title || "Title")}
                    {pick.year ? ` (${pick.year})` : ""}
                  </span>
                  {shelfPickRole(String(pick.role || pick.shelf_role || "")) ? (
                    <span className="live-shelf-title-role">
                      {shelfPickRole(String(pick.role || pick.shelf_role || ""))}
                    </span>
                  ) : null}
                  <span>{String(pick.curator_note || pick.note || "")}</span>
                  {pick.matched_because ? <span>Why it matched: {String(pick.matched_because)}</span> : null}
                </li>
              ))}
            </ol>
            <div className="live-shelf-proposal-actions">
              <button
                type="button"
                className="primary"
                disabled={busy}
                data-testid={`live-shelf-apply-${item.id}`}
                onClick={() =>
                  void run(async () => {
                    const applied = (await applyHolidayRailCuration(item.id, proposal.applyPicks, {
                      theme: proposal.theme,
                    })) as { preview?: ShelfRail };
                    if (applied?.preview) setRail(applied.preview);
                    else await loadRail();
                    setProposal(null);
                    setNoteDrafts({});
                    onSaved?.(null);
                  }, "Shelf updated. These picks are what Explore shows.")
                }
              >
                Apply
              </button>
              <button
                type="button"
                className="ghost"
                disabled={busy}
                data-testid={`live-shelf-redo-${item.id}`}
                onClick={() =>
                  void run(async () => {
                    const result = (await proposeHolidayRailCuration(item.id, {
                      limit: 10,
                      role_mix: mix,
                    })) as { picks?: unknown[]; theme?: string };
                    const plan = curateClickPlan({ proposal: result });
                    if (!plan.ok) throw new Error(plan.message);
                    setProposal({
                      theme: plan.theme,
                      picks: (result.picks || []) as Array<Record<string, unknown>>,
                      applyPicks: plan.applyPicks as Array<Record<string, unknown>>,
                    });
                  })
                }
              >
                Redo
              </button>
              <button
                type="button"
                className="ghost"
                disabled={busy}
                data-testid={`live-shelf-cancel-${item.id}`}
                onClick={() => setProposal(null)}
              >
                Cancel
              </button>
            </div>
          </div>
        ) : null}
        {message ? (
          <p
            className={`live-studio-note live-studio-note--${message.type}`}
            role={message.type === "error" ? "alert" : "status"}
            data-testid={`live-shelf-message-${item.id}`}
          >
            {message.text}
          </p>
        ) : null}

        {titles.length ? (
          <ol className="live-shelf-titles" data-testid={`live-shelf-titles-${item.id}`}>
            {titles.map((row, index) => {
              const note = noteFor(row);
              const hasNote = Boolean(String(row.curator_note || row.why || "").trim());
              const pickRole = shelfPickRole(row.shelf_role || row.role);
              return (
                <li key={row.id} data-testid={`live-shelf-title-${item.id}-${row.id}`}>
                  <div className="live-shelf-title-row">
                    <button
                      type="button"
                      className="ghost"
                      draggable={!busy}
                      aria-label={`Drag ${row.title || "title"}`}
                      disabled={busy}
                      onDragStart={() => setDragIndex(index)}
                      onDragOver={(event) => event.preventDefault()}
                      onDrop={() => {
                        if (dragIndex == null || dragIndex === index) return;
                        const next = [...ids];
                        const [moved] = next.splice(dragIndex, 1);
                        next.splice(index, 0, moved);
                        setDragIndex(null);
                        void saveOrder(next);
                      }}
                    >
                      Drag
                    </button>
                    <span className="live-shelf-title-name">
                      {row.title}
                      {row.year ? ` (${row.year})` : ""}
                    </span>
                    <span className="live-shelf-title-role">
                      {pickRole || shelfRoleLabel(row.rail_role, { hasNote })}
                    </span>
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
                        data-testid={`live-shelf-chat-${item.id}-${row.id}`}
                        onClick={() => setChatTitle(row)}
                      >
                        Chat about this
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
                            if (Number(chatTitle?.id) === Number(row.id)) setChatTitle(null);
                            await loadRail();
                          }, `${row.title} is off this shelf.`)
                        }
                      >
                        Not a fit
                      </button>
                    </span>
                  </div>
                  {row.matched_because ? (
                    <p className="live-studio-hint">Why it matched: {row.matched_because}</p>
                  ) : null}
                  <label className="live-shelf-note-field">
                    <span className="sr-only">Curator note for {row.title}</span>
                    <textarea
                      rows={2}
                      value={note}
                      placeholder="Staff-pick note — why this title for this season"
                      data-testid={`live-shelf-note-${item.id}-${row.id}`}
                      disabled={busy}
                      onChange={(event) =>
                        setNoteDrafts((prev) => ({
                          ...prev,
                          [Number(row.id)]: event.target.value,
                        }))
                      }
                      onBlur={() => {
                        const next = String(noteDrafts[Number(row.id)] ?? note).trim();
                        const saved = String(row.curator_note || row.why || "").trim();
                        if (next === saved) return;
                        void run(async () => {
                          const result = (await setHolidayRailCuratorNote(
                            item.id,
                            Number(row.id),
                            next,
                          )) as { preview?: ShelfRail };
                          if (result?.preview) setRail(result.preview);
                          else await loadRail();
                          setNoteDrafts((prev) => {
                            const copy = { ...prev };
                            delete copy[Number(row.id)];
                            return copy;
                          });
                        }, "Note saved.");
                      }}
                    />
                  </label>
                </li>
              );
            })}
          </ol>
        ) : (
          <p className="live-studio-hint" data-testid={`live-shelf-empty-${item.id}`}>
            Nothing in your library matches this season yet. Ask the professor after you widen
            the keywords, or add a title below.
          </p>
        )}

        <form
          className="live-shelf-add"
          onSubmit={async (event) => {
            event.preventDefault();
            if (!query.trim()) return;
            await run(async () => {
              const result = (await searchHolidayLibrary(query.trim(), { limit: 8 })) as { items?: LibraryHit[] };
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

        {showCalendar ? (
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
                  const saved = (await updateHoliday(item.id, shelfPatchFromForm(form, item))) as { item?: ShelfItem };
                  onSaved?.(saved?.item || null);
                  await loadRail();
                }, "Shelf saved.")
              }
            >
              Save shelf
            </button>
          </div>
        </details>
        ) : null}
      </div>

      {chatOpen ? (
        <SeasonalPickChatPane
          seasonLabel={item.name}
          scopeId={item.id as any}
          title={chatTitle}
          onClose={() => setChatTitle(null)}
          testId={`live-shelf-chat-${item.id}`}
        />
      ) : null}
    </div>
  );
}

/** Live keeps channel settings. Holiday shelves live on Holidays & seasons. */
export default function SeasonalShelves() {
  return (
    <section className="live-studio-card live-shelves" data-testid="live-holiday-shelves-link">
      <header className="live-studio-card-head">
        <div>
          <h3>Holiday shelves</h3>
          <p className="live-studio-hint">
            Themes, picks, dates, and Live blocks for the seasons on Explore are on one page.
          </p>
        </div>
      </header>
      <p className="live-studio-hint">
        <Link to="/admin/holidays" className="btn-link" data-testid="live-open-holidays">
          Holidays & seasons
        </Link>
      </p>
    </section>
  );
}

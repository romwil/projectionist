import { useCallback, useEffect, useState } from "react";
import {
  addCuratedListItem,
  createCuratedList,
  deleteCuratedList,
  deleteCuratedListItem,
  formatApiError,
  getCuratedList,
  listCuratedLists,
  listWatchlist,
  updateCuratedList,
} from "../../api/client";

export default function ListsSettingsPage() {
  const [lists, setLists] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [watchlistPins, setWatchlistPins] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);
  const [newName, setNewName] = useState("");
  const [renameValue, setRenameValue] = useState("");
  const [manualTitle, setManualTitle] = useState("");
  const [manualMediaType, setManualMediaType] = useState("movie");
  const [manualTmdbId, setManualTmdbId] = useState("");
  const [manualTvdbId, setManualTvdbId] = useState("");
  const [watchlistPick, setWatchlistPick] = useState("");

  const refreshLists = useCallback(async () => {
    const next = await listCuratedLists();
    setLists(next.items || []);
    return next.items || [];
  }, []);

  const refreshDetail = useCallback(async (listId) => {
    if (!listId) {
      setDetail(null);
      return;
    }
    const next = await getCuratedList(listId);
    setDetail(next);
    setRenameValue(next?.name || "");
  }, []);

  const bootstrap = useCallback(async () => {
    setLoading(true);
    try {
      const [items, watchlist] = await Promise.all([refreshLists(), listWatchlist().catch(() => ({ items: [] }))]);
      setWatchlistPins(watchlist.items || []);
      const nextSelected = selectedId && items.some((item) => item.id === selectedId) ? selectedId : items[0]?.id || null;
      setSelectedId(nextSelected);
      if (nextSelected) {
        await refreshDetail(nextSelected);
      } else {
        setDetail(null);
      }
      setMessage(null);
    } catch (error) {
      setMessage({ type: "error", text: formatApiError(error) });
    } finally {
      setLoading(false);
    }
  }, [refreshDetail, refreshLists, selectedId]);

  useEffect(() => {
    bootstrap();
    // Intentionally mount-only; select changes load via handlers.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleCreate(event) {
    event.preventDefault();
    const name = newName.trim();
    if (!name) return;
    setSaving(true);
    setMessage(null);
    try {
      const created = await createCuratedList({ name });
      setNewName("");
      await refreshLists();
      setSelectedId(created.id);
      await refreshDetail(created.id);
      setMessage({ type: "success", text: `Created “${created.name}”.` });
    } catch (error) {
      setMessage({ type: "error", text: formatApiError(error) });
    } finally {
      setSaving(false);
    }
  }

  async function handleRename(event) {
    event.preventDefault();
    if (!selectedId) return;
    const name = renameValue.trim();
    if (!name) return;
    setSaving(true);
    setMessage(null);
    try {
      const updated = await updateCuratedList(selectedId, { name });
      await refreshLists();
      setDetail(updated);
      setMessage({ type: "success", text: "List renamed." });
    } catch (error) {
      setMessage({ type: "error", text: formatApiError(error) });
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteList() {
    if (!selectedId || !detail) return;
    if (!window.confirm(`Delete list “${detail.name}”?`)) return;
    setSaving(true);
    setMessage(null);
    try {
      await deleteCuratedList(selectedId);
      const items = await refreshLists();
      const nextId = items[0]?.id || null;
      setSelectedId(nextId);
      await refreshDetail(nextId);
      setMessage({ type: "success", text: "List deleted." });
    } catch (error) {
      setMessage({ type: "error", text: formatApiError(error) });
    } finally {
      setSaving(false);
    }
  }

  async function handleSelect(listId) {
    setSelectedId(listId);
    setMessage(null);
    try {
      await refreshDetail(listId);
    } catch (error) {
      setMessage({ type: "error", text: formatApiError(error) });
    }
  }

  async function handleAddManual(event) {
    event.preventDefault();
    if (!selectedId) return;
    const title = manualTitle.trim();
    const tmdbId = manualTmdbId.trim() ? Number(manualTmdbId) : null;
    const tvdbId = manualTvdbId.trim() ? Number(manualTvdbId) : null;
    if (!title || (!tmdbId && !tvdbId)) {
      setMessage({ type: "error", text: "Title and a TMDB or TVDB id are required." });
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      await addCuratedListItem(selectedId, {
        title,
        media_type: manualMediaType,
        tmdb_id: tmdbId,
        tvdb_id: tvdbId,
      });
      setManualTitle("");
      setManualTmdbId("");
      setManualTvdbId("");
      await Promise.all([refreshLists(), refreshDetail(selectedId)]);
      setMessage({ type: "success", text: `Added “${title}”.` });
    } catch (error) {
      setMessage({ type: "error", text: formatApiError(error) });
    } finally {
      setSaving(false);
    }
  }

  async function handleAddFromWatchlist(event) {
    event.preventDefault();
    if (!selectedId || !watchlistPick) return;
    const pin = watchlistPins.find((entry) => entry.id === watchlistPick);
    if (!pin) return;
    setSaving(true);
    setMessage(null);
    try {
      await addCuratedListItem(selectedId, {
        title: pin.title,
        media_type: pin.media_type,
        tmdb_id: pin.tmdb_id ?? null,
        tvdb_id: pin.tvdb_id ?? null,
      });
      setWatchlistPick("");
      await Promise.all([refreshLists(), refreshDetail(selectedId)]);
      setMessage({ type: "success", text: `Added “${pin.title}” from watchlist.` });
    } catch (error) {
      setMessage({ type: "error", text: formatApiError(error) });
    } finally {
      setSaving(false);
    }
  }

  async function handleRemoveItem(item) {
    if (!selectedId) return;
    setSaving(true);
    setMessage(null);
    try {
      await deleteCuratedListItem(selectedId, item.id);
      await Promise.all([refreshLists(), refreshDetail(selectedId)]);
      setMessage({ type: "success", text: `Removed “${item.title}”.` });
    } catch (error) {
      setMessage({ type: "error", text: formatApiError(error) });
    } finally {
      setSaving(false);
    }
  }

  if (loading && !lists.length) {
    return (
      <section className="settings-section" data-testid="settings-lists">
        <h2>Lists</h2>
        <p className="status status-secondary">Loading lists…</p>
      </section>
    );
  }

  return (
    <section className="settings-section" data-testid="settings-lists">
      <header className="settings-section-header">
        <h2>Lists</h2>
        <p>
          Named shelves on CuratorX. Lists stay local for now — Plex Discover personal Lists have no
          public publish API yet.
        </p>
      </header>

      <form className="settings-form lists-create-form" onSubmit={handleCreate} data-testid="lists-create-form">
        <label>
          New list name
          <input
            type="text"
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
            placeholder="Weekend sci-fi"
            data-testid="lists-create-name"
            disabled={saving}
          />
        </label>
        <div className="config-actions">
          <button type="submit" disabled={saving || !newName.trim()} data-testid="lists-create-submit">
            Create list
          </button>
        </div>
      </form>

      <div className="lists-layout">
        <div className="settings-subsection" data-testid="lists-index">
          <h3>Your lists</h3>
          {lists.length ? (
            <ul className="lists-index-list">
              {lists.map((list) => (
                <li key={list.id}>
                  <button
                    type="button"
                    className={`lists-index-item ${selectedId === list.id ? "lists-index-item-active" : ""}`}
                    data-testid={`lists-select-${list.id}`}
                    onClick={() => handleSelect(list.id)}
                  >
                    <span className="lists-index-name">{list.name}</span>
                    <span className="lists-index-count">{list.item_count ?? 0}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="status status-secondary">No lists yet — create one above.</p>
          )}
        </div>

        {detail ? (
          <div className="settings-subsection" data-testid="lists-detail">
            <h3>{detail.name}</h3>
            <form className="settings-form" onSubmit={handleRename}>
              <label>
                Rename
                <input
                  type="text"
                  value={renameValue}
                  onChange={(event) => setRenameValue(event.target.value)}
                  data-testid="lists-rename-input"
                  disabled={saving}
                />
              </label>
              <div className="config-actions">
                <button type="submit" disabled={saving || !renameValue.trim()} data-testid="lists-rename-submit">
                  Save name
                </button>
                <button
                  type="button"
                  className="ghost"
                  disabled={saving}
                  data-testid="lists-delete"
                  onClick={handleDeleteList}
                >
                  Delete list
                </button>
              </div>
            </form>

            <ul className="lists-item-list" data-testid="lists-items">
              {(detail.items || []).map((item) => (
                <li key={item.id} className="lists-item-row">
                  <div>
                    <span className="lists-item-title">{item.title}</span>
                    <span className="lists-item-meta">
                      {item.media_type === "show" ? "Show" : "Movie"}
                      {item.library_item_id ? " · in library" : ""}
                    </span>
                  </div>
                  <button
                    type="button"
                    className="ghost"
                    data-testid={`lists-remove-${item.id}`}
                    disabled={saving}
                    onClick={() => handleRemoveItem(item)}
                    aria-label={`Remove ${item.title}`}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
            {!detail.items?.length ? (
              <p className="status status-secondary">This list is empty.</p>
            ) : null}

            <form className="settings-form" onSubmit={handleAddFromWatchlist} data-testid="lists-add-watchlist-form">
              <label>
                Add from watchlist
                <select
                  value={watchlistPick}
                  onChange={(event) => setWatchlistPick(event.target.value)}
                  data-testid="lists-watchlist-select"
                  disabled={saving || !watchlistPins.length}
                >
                  <option value="">
                    {watchlistPins.length ? "Choose a pin…" : "No watchlist pins"}
                  </option>
                  {watchlistPins.map((pin) => (
                    <option key={pin.id} value={pin.id}>
                      {pin.title}
                    </option>
                  ))}
                </select>
              </label>
              <div className="config-actions">
                <button type="submit" disabled={saving || !watchlistPick} data-testid="lists-add-watchlist">
                  Add from watchlist
                </button>
              </div>
            </form>

            <form className="settings-form" onSubmit={handleAddManual} data-testid="lists-add-manual-form">
              <label>
                Title
                <input
                  type="text"
                  value={manualTitle}
                  onChange={(event) => setManualTitle(event.target.value)}
                  data-testid="lists-manual-title"
                  disabled={saving}
                />
              </label>
              <label>
                Media type
                <select
                  value={manualMediaType}
                  onChange={(event) => setManualMediaType(event.target.value)}
                  data-testid="lists-manual-media-type"
                  disabled={saving}
                >
                  <option value="movie">Movie</option>
                  <option value="show">Show</option>
                </select>
              </label>
              <label>
                TMDB id
                <input
                  type="number"
                  value={manualTmdbId}
                  onChange={(event) => setManualTmdbId(event.target.value)}
                  data-testid="lists-manual-tmdb"
                  disabled={saving}
                />
              </label>
              <label>
                TVDB id
                <input
                  type="number"
                  value={manualTvdbId}
                  onChange={(event) => setManualTvdbId(event.target.value)}
                  data-testid="lists-manual-tvdb"
                  disabled={saving}
                />
              </label>
              <div className="config-actions">
                <button type="submit" disabled={saving} data-testid="lists-add-manual">
                  Add title
                </button>
              </div>
            </form>
          </div>
        ) : null}
      </div>

      {message ? (
        <p
          className={`status ${message.type === "error" ? "status-error" : ""}`}
          data-testid="lists-message"
        >
          {message.text}
        </p>
      ) : null}
    </section>
  );
}

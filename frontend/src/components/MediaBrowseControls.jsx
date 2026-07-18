import { useEffect, useState } from "react";
import {
  MEDIA_BROWSE_COLUMNS,
  MEDIA_BROWSE_SORTS,
  libraryExportHref,
  loadMediaBrowseColumns,
  saveMediaBrowseColumns,
} from "../lib/mediaBrowse.js";

export default function MediaBrowseControls({
  state,
  onChange,
  columns,
  onColumnsChange,
  columnScope = "library",
  filterOptions = {},
  bulkActions,
  leading,
  exportEnabled = true,
}) {
  const [columnOpen, setColumnOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const visibleColumns = columns || loadMediaBrowseColumns(columnScope);

  useEffect(() => {
    if (columns) return;
    onColumnsChange?.(loadMediaBrowseColumns(columnScope));
  }, [columnScope, columns, onColumnsChange]);

  function update(patch) {
    onChange?.({ ...patch, ...(Object.hasOwn(patch, "offset") ? {} : { offset: 0 }) });
  }

  function toggleColumn(id) {
    const next = visibleColumns.includes(id)
      ? visibleColumns.filter((column) => column !== id)
      : [...visibleColumns, id];
    if (!next.length) return;
    saveMediaBrowseColumns(columnScope, next);
    onColumnsChange?.(next);
  }

  return (
    <div className="media-browse-controls" data-testid="media-browse-controls">
      <div className="media-browse-controls-main">
        {leading}
        <label>
          <span>Sort</span>
          <select value={state.sort} onChange={(event) => update({ sort: event.target.value })}>
            {MEDIA_BROWSE_SORTS.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
          </select>
        </label>
        <button type="button" className="ghost" onClick={() => update({ sort_dir: state.sort_dir === "asc" ? "desc" : "asc" })}>
          {state.sort_dir === "asc" ? "↑ Asc" : "↓ Desc"}
        </button>
        <label>
          <span>Type</span>
          <select value={state.media_type || ""} onChange={(event) => update({ media_type: event.target.value })}>
            <option value="">All</option><option value="movie">Movies</option><option value="show">TV shows</option>
          </select>
        </label>
        <label>
          <span>Watch</span>
          <select value={state.watch_state || ""} onChange={(event) => update({ watch_state: event.target.value })}>
            <option value="">Any</option><option value="unwatched">Unwatched</option><option value="in_progress">In progress</option><option value="watched">Watched</option>
          </select>
        </label>
        {filterOptions.years?.length ? (
          <label><span>Year</span><select value={state.year || ""} onChange={(event) => update({ year: event.target.value })}>
            <option value="">Any</option>{filterOptions.years.map((year) => <option key={year} value={year}>{year}</option>)}
          </select></label>
        ) : null}
      </div>
      <div className="media-browse-controls-actions">
        {bulkActions}
        <div className="media-browse-menu-wrap">
          <button type="button" className="ghost" aria-expanded={columnOpen} onClick={() => setColumnOpen((open) => !open)}>Columns</button>
          {columnOpen ? <div className="media-browse-popover" role="menu">
            {MEDIA_BROWSE_COLUMNS.map((column) => <label key={column.id}>
              <input type="checkbox" checked={visibleColumns.includes(column.id)} onChange={() => toggleColumn(column.id)} />
              {column.label}
            </label>)}
          </div> : null}
        </div>
        <div className="media-browse-menu-wrap">
          <button type="button" className="ghost" aria-expanded={exportOpen} disabled={!exportEnabled} onClick={() => setExportOpen((open) => !open)}>Export CSV</button>
          {exportOpen ? <div className="media-browse-popover" role="menu">
            <a href={libraryExportHref(state, visibleColumns)}>Visible columns</a>
            <a href={libraryExportHref(state)}>All columns</a>
          </div> : null}
        </div>
        <div className="media-browse-view-toggle" aria-label="View">
          <button type="button" className={state.view === "poster" ? "is-active" : ""} onClick={() => update({ view: "poster" })}>Posters</button>
          <button type="button" className={state.view === "list" ? "is-active" : ""} onClick={() => update({ view: "list" })}>List</button>
        </div>
      </div>
    </div>
  );
}

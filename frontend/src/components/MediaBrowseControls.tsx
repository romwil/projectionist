import { useEffect, useState } from "react";
import {
  MEDIA_BROWSE_COLUMNS,
  MEDIA_BROWSE_SORTS,
  browseTypeChoices,
  libraryExportHref,
  normalizeBrowseMediaType,
  loadMediaBrowseColumns,
  saveMediaBrowseColumns,
} from "../lib/mediaBrowse.js";
import { formatLanguageName, isKnownLanguageCode, normalizeLanguageCode } from "../lib/languageNames.js";

function browseLanguageChoices(options: any, current: any) {
  const list = [];
  const seen = new Set();
  for (const entry of options || []) {
    const code = normalizeLanguageCode(typeof entry === "string" ? entry : entry?.code);
    if (!code || seen.has(code) || !isKnownLanguageCode(code)) continue;
    seen.add(code);
    const label =
      typeof entry === "object" && entry?.label ? entry.label : formatLanguageName(code);
    list.push({ code, label });
  }
  const selected = normalizeLanguageCode(current);
  if (selected && !seen.has(selected)) {
    list.push({ code: selected, label: formatLanguageName(selected) });
  }
  return list;
}

/** Props for MediaBrowseControls. `any` = API/handler bags until Wave 4 client generics. */
type MediaBrowseControlsProps = {
  state?: any;
  onChange?: (...args: any[]) => void;
  columns?: any;
  onColumnsChange?: (...args: any[]) => void;
  columnScope?: any;
  filterOptions?: any;
  bulkActions?: any;
  leading?: React.ReactNode;
  exportEnabled?: any;
  sortOptions?: any;
  exportItems?: any;
  onExport?: (...args: any[]) => void;
  pageSizes?: any;
  mediaTypeScope?: any;
};

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
  sortOptions = MEDIA_BROWSE_SORTS,
  exportItems,
  onExport,
  pageSizes,
  mediaTypeScope = "",
}: MediaBrowseControlsProps) {
  const [columnOpen, setColumnOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const visibleColumns = columns || loadMediaBrowseColumns(columnScope);

  useEffect(() => {
    if (columns) return;
    onColumnsChange?.(loadMediaBrowseColumns(columnScope));
  }, [columnScope, columns, onColumnsChange]);

  function update(patch: any) {
    onChange?.({ ...patch, ...(Object.hasOwn(patch, "offset") ? {} : { offset: 0 }) });
  }

  function toggleColumn(id: any) {
    const next = visibleColumns.includes(id)
      ? visibleColumns.filter((column: any) => column !== id)
      : [...visibleColumns, id];
    if (!next.length) return;
    saveMediaBrowseColumns(columnScope, next);
    onColumnsChange?.(next);
  }

  function updateList(key: any, value: any) {
    const values = Array.isArray(state[key]) ? state[key] : [];
    update({
      [key]: values.includes(value)
        ? values.filter((entry) => entry !== value)
        : [...values, value],
    });
  }

  const typeChoices = browseTypeChoices(mediaTypeScope);
  const normalizedType = normalizeBrowseMediaType(state.media_type) || "";
  const typeValue = typeChoices.some((choice) => choice.value === normalizedType)
    ? normalizedType
    : typeChoices[0].value;
  const languageChoices = browseLanguageChoices(filterOptions.languages, state.language);

  return (
    <div className="media-browse-controls" data-testid="media-browse-controls">
      <div className="media-browse-controls-main">
        {leading}
        <div className="media-browse-control-group media-browse-filter-controls">
          <label>
            <span>Type</span>
            <select
              value={typeValue}
              data-testid="media-browse-type"
              onChange={(event) => {
                if (mediaTypeScope) return;
                update({ media_type: normalizeBrowseMediaType(event.target.value) });
              }}
            >
              {typeChoices.map((choice) => (
                <option key={choice.value || "all"} value={choice.value}>
                  {choice.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Watch</span>
            <select
              value={state.watch_state || ""}
              onChange={(event) => update({ watch_state: event.target.value })}
            >
              <option value="">Any</option>
              <option value="unwatched">Unwatched</option>
              <option value="in_progress">In progress</option>
              <option value="watched">Watched</option>
            </select>
          </label>
          {filterOptions.years?.length ? (
            <label>
              <span>Year</span>
              <select
                value={state.year || ""}
                onChange={(event) => update({ year: event.target.value })}
              >
                <option value="">Any</option>
                {filterOptions.years.map((year: any) => (
                  <option key={year} value={year}>
                    {year}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {languageChoices.length ? (
            <label>
              <span>Language</span>
              <select
                value={normalizeLanguageCode(state.language) || ""}
                data-testid="media-browse-language"
                onChange={(event) => update({ language: event.target.value })}
              >
                <option value="">Any</option>
                {languageChoices.map((language) => (
                  <option key={language.code} value={language.code}>
                    {language.label}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {filterOptions.genres?.length ? (
            <details className="media-browse-filter-menu">
              <summary>Genres{state.genres?.length ? ` (${state.genres.length})` : ""}</summary>
              <div className="media-browse-popover">
                <span>Genres</span>
                {filterOptions.genres.map((genre: any) => (
                  <label key={genre}>
                    <input
                      type="checkbox"
                      checked={state.genres?.includes(genre)}
                      onChange={() => updateList("genres", genre)}
                    />
                    {genre}
                  </label>
                ))}
              </div>
            </details>
          ) : null}
        </div>
        <div className="media-browse-control-group media-browse-sort-controls">
          <label>
            <span>Sort by</span>
            <select value={state.sort} onChange={(event) => update({ sort: event.target.value })}>
              {sortOptions.map((option: any) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="ghost media-browse-sort-direction"
            aria-label={`Sort ${state.sort_dir === "asc" ? "descending" : "ascending"}`}
            onClick={() => update({ sort_dir: state.sort_dir === "asc" ? "desc" : "asc" })}
          >
            {state.sort_dir === "asc" ? "↑ Asc" : "↓ Desc"}
          </button>
        </div>
      </div>
      <div className="media-browse-controls-actions">
        {bulkActions}
        <div className="media-browse-view-control">
          <span>View</span>
          <div className="media-browse-view-toggle" aria-label="View">
            <button
              type="button"
              className={state.view === "poster" ? "is-active" : ""}
              onClick={() => update({ view: "poster" })}
            >
              Posters
            </button>
            <button
              type="button"
              className={state.view === "list" ? "is-active" : ""}
              onClick={() => update({ view: "list" })}
            >
              List
            </button>
          </div>
        </div>
        {pageSizes?.length ? (
          <label>
            <span>Per page</span>
            <select
              value={String(state.limit)}
              data-testid="media-browse-page-size"
              onChange={(event) => {
                const raw = event.target.value;
                update({ limit: raw === "all" ? "all" : Number(raw) });
              }}
            >
              {pageSizes.map((size: any) => (
                <option key={String(size)} value={String(size)}>
                  {String(size).toLowerCase() === "all" ? "All" : size}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <div className="media-browse-secondary-actions" aria-label="Display and export options">
          <div className="media-browse-menu-wrap">
            <button
              type="button"
              className="ghost"
              aria-expanded={columnOpen}
              onClick={() => setColumnOpen((open) => !open)}
            >
              Columns
            </button>
            {columnOpen ? (
              <div className="media-browse-popover" role="menu">
                {MEDIA_BROWSE_COLUMNS.map((column) => (
                  <label key={column.id}>
                    <input
                      type="checkbox"
                      checked={visibleColumns.includes(column.id)}
                      onChange={() => toggleColumn(column.id)}
                    />
                    {column.label}
                  </label>
                ))}
              </div>
            ) : null}
          </div>
          <div className="media-browse-menu-wrap">
            <button
              type="button"
              className="ghost"
              aria-expanded={exportOpen}
              disabled={!exportEnabled}
              onClick={() => setExportOpen((open) => !open)}
            >
              Export CSV
            </button>
            {exportOpen ? (
              <div className="media-browse-popover" role="menu">
                {exportItems ? (
                  <>
                    <button type="button" onClick={() => onExport?.(visibleColumns)}>
                      Current page · visible columns
                    </button>
                    <button
                      type="button"
                      onClick={() => onExport?.(MEDIA_BROWSE_COLUMNS.map((column) => column.id))}
                    >
                      Current page · all columns
                    </button>
                  </>
                ) : (
                  <>
                    <a href={libraryExportHref(state, visibleColumns)}>Visible columns</a>
                    <a href={libraryExportHref(state)}>All columns</a>
                  </>
                )}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

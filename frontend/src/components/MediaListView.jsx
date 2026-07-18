import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import PosterActionMenu from "./PosterActionMenu";
import { mediaBrowseWatchState } from "../lib/mediaBrowse.js";
import { titleDetailPath } from "../lib/titleLinks.js";

const columnWidths = {
  title: "minmax(220px, 2.5fr)",
  year: "58px",
  media_type: "74px",
  rating: "62px",
  genres: "minmax(130px, 1.1fr)",
  runtime: "72px",
  watch_state: "104px",
};

function columnLabel(column) {
  return column === "media_type" ? "Type" : column.replace("_", " ");
}

function watchStateLabel(item) {
  return mediaBrowseWatchState(item).replace("_", " ").replace(/^./, (char) => char.toUpperCase());
}

export default function MediaListView({
  items,
  columns = ["title", "year", "media_type", "rating", "genres", "watch_state"],
  selected,
  onToggleSelect,
  selectable = false,
  onRecommend,
  onSeed,
  onTogglePin,
  getItemKey,
  cardProps = {},
}) {
  const [preview, setPreview] = useState(null);
  const previewTimer = useRef(null);
  const gridTemplate = ["32px", selectable ? "34px" : null, ...columns.map((column) => columnWidths[column] || "minmax(90px, 1fr)")].filter(Boolean).join(" ");

  useEffect(() => () => window.clearTimeout(previewTimer.current), []);

  function clearPreviewTimer() {
    window.clearTimeout(previewTimer.current);
  }

  function schedulePreview(item, position) {
    if (!item.poster_url) return;
    clearPreviewTimer();
    previewTimer.current = window.setTimeout(() => {
      const width = 160;
      const height = 240;
      setPreview({
        item,
        left: Math.max(12, Math.min(position.left, window.innerWidth - width - 12)),
        top: Math.max(12, Math.min(position.top, window.innerHeight - height - 12)),
      });
    }, 180);
  }

  function hidePreview() {
    clearPreviewTimer();
    previewTimer.current = window.setTimeout(() => setPreview(null), 100);
  }

  return <div className="media-list-scroll">
    <div className="media-list-view" role="table" aria-label="Titles" style={{ "--media-list-columns": gridTemplate }}>
      <div className="media-list-row media-list-header" role="row">
        <span aria-hidden="true" />
        {selectable ? <span aria-hidden="true" /> : null}
        {columns.map((column) => <span key={column} role="columnheader">{columnLabel(column)}</span>)}
      </div>
      {items.map((item) => {
        const key = getItemKey?.(item) || String(item.id || item.rating_key || item.plex_rating_key || `${item.media_type}:${item.tmdb_id || item.title}`);
        const path = titleDetailPath({ ...item, in_library: true });
        const itemCardProps = typeof cardProps === "function" ? cardProps(item) : cardProps;
        const showInlineWatchState = !columns.includes("watch_state") && mediaBrowseWatchState(item) !== "unwatched";
        return <div className="media-list-row" role="row" key={key}>
          <PosterActionMenu
            item={item}
            onRecommend={onRecommend}
            onSeed={onSeed}
            onTogglePin={onTogglePin}
            {...itemCardProps}
          />
          {selectable ? <label className="media-list-select"><input type="checkbox" checked={selected?.has(key)} onChange={() => onToggleSelect?.(item)} /><span className="sr-only">Select {item.title}</span></label> : null}
          {columns.map((column) => <span key={column} role="cell" data-column={column}>
            {column === "title" ? <span
              className="media-list-title"
              onPointerEnter={(event) => schedulePreview(item, { left: event.clientX + 16, top: event.clientY + 16 })}
              onPointerLeave={hidePreview}
              onFocus={(event) => {
                const rect = event.currentTarget.getBoundingClientRect();
                schedulePreview(item, { left: rect.right + 12, top: rect.top });
              }}
              onBlur={hidePreview}
            >
              {path ? <Link to={path}>{item.title || "Untitled"}</Link> : item.title || "Untitled"}
              {showInlineWatchState ? <span className={`media-list-watch-state is-${mediaBrowseWatchState(item)}`}>{watchStateLabel(item)}</span> : null}
            </span> :
              column === "genres" ? (item.genres || []).slice(0, 3).join(" · ") :
                column === "watch_state" ? <span className={`media-list-watch-state is-${mediaBrowseWatchState(item)}`}>{watchStateLabel(item)}</span> :
                  item[column] ?? "—"}
          </span>)}
        </div>;
      })}
    </div>
    {preview ? <div
      className="media-list-poster-preview"
      role="tooltip"
      style={{ left: preview.left, top: preview.top }}
      onPointerEnter={clearPreviewTimer}
      onPointerLeave={hidePreview}
    >
      <img src={preview.item.poster_url} alt={`Poster for ${preview.item.title || "title"}`} />
    </div> : null}
  </div>;
}

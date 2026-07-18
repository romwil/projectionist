import { Link } from "react-router-dom";
import PosterActionMenu from "./PosterActionMenu";
import WatchProgressBadge from "./WatchProgressBadge";
import { titleDetailPath } from "../lib/titleLinks.js";

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
  return <div className="media-list-view" role="table" aria-label="Titles">
    <div className="media-list-row media-list-header" role="row">
      {selectable ? <span /> : null}
      {columns.map((column) => <span key={column} role="columnheader">{column.replace("_", " ")}</span>)}
      <span />
    </div>
    {items.map((item) => {
      const key = getItemKey?.(item) || String(item.id || item.rating_key || item.plex_rating_key || `${item.media_type}:${item.tmdb_id || item.title}`);
      const path = titleDetailPath({ ...item, in_library: true });
      const itemCardProps = typeof cardProps === "function" ? cardProps(item) : cardProps;
      return <div className="media-list-row" role="row" key={key}>
        {selectable ? <label><input type="checkbox" checked={selected?.has(key)} onChange={() => onToggleSelect?.(item)} /><span className="sr-only">Select {item.title}</span></label> : null}
        {columns.map((column) => <span key={column} role="cell" data-column={column}>
          {column === "title" ? <>{item.poster_url ? <img className="media-list-poster" src={item.poster_url} alt="" /> : null}{path ? <Link to={path}>{item.title || "Untitled"}</Link> : item.title || "Untitled"}<WatchProgressBadge item={item} /></> :
            column === "genres" ? (item.genres || []).slice(0, 3).join(" · ") :
              column === "watch_state" ? (item.watched ? "Watched" : item.view_offset ? "In progress" : "Unwatched") :
                item[column] ?? "—"}
        </span>)}
        <PosterActionMenu
          item={item}
          onRecommend={onRecommend}
          onSeed={onSeed}
          onTogglePin={onTogglePin}
          {...itemCardProps}
        />
      </div>;
    })}
  </div>;
}

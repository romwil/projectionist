import LibraryMediaCard from "./LibraryMediaCard";
import MediaListView from "./MediaListView";

export default function MediaBrowseResults({
  state,
  items,
  columns,
  selected,
  onToggleSelect,
  selectable = false,
  cardProps = {},
}) {
  if (state.view === "list") {
    return <MediaListView items={items} columns={columns} selected={selected} onToggleSelect={onToggleSelect} selectable={selectable} {...cardProps} />;
  }
  return <div className="explore-poster-wall media-browse-poster-wall">
    {items.map((item) => {
      const key = String(item.id || item.rating_key || item.plex_rating_key || `${item.media_type}:${item.tmdb_id || item.title}`);
      const isSelected = selected?.has(key);
      const itemCardProps = typeof cardProps === "function" ? cardProps(item) : cardProps;
      return <div key={key} className={`explore-section-card-wrap${isSelected ? " is-selected" : ""}`}>
        {selectable ? <label className="explore-section-select">
          <input type="checkbox" checked={isSelected} onChange={() => onToggleSelect?.(item)} />
          <span className="sr-only">Select {item.title || "title"}</span>
        </label> : null}
        <LibraryMediaCard item={item} {...itemCardProps} />
      </div>;
    })}
  </div>;
}

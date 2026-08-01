import { titleDetailPath } from "../lib/titleLinks.js";
import TitleDetailLink from "./TitleDetailLink";

export default function OnThisDayCard({ items, accentColor }) {
  if (!items?.length) return null;

  return (
    <section
      className="on-this-day-card"
      data-testid="on-this-day-card"
      style={accentColor ? { "--otd-accent": accentColor } : undefined}
    >
      <h4 className="on-this-day-heading">On This Day</h4>
      <div className="on-this-day-scroll">
        {items.slice(0, 3).map((item) => {
          const path = titleDetailPath(item);
          const body = (
            <>
              {item.poster_url ? (
                <img
                  className="on-this-day-poster"
                  src={item.poster_url}
                  alt=""
                  loading="lazy"
                />
              ) : (
                <div className="on-this-day-poster-fallback">
                  {item.title?.slice(0, 1) || "?"}
                </div>
              )}
              <div className="on-this-day-meta">
                <p className="on-this-day-title">{item.title}</p>
                <p className="on-this-day-context">{item.anniversary_context}</p>
              </div>
            </>
          );
          const key = item.tmdb_id || item.rating_key || item.title;
          return path ? (
            <TitleDetailLink
              key={key}
              item={item}
              className="on-this-day-item"
              data-testid="on-this-day-item-link"
            >
              {body}
            </TitleDetailLink>
          ) : (
            <article key={key} className="on-this-day-item">
              {body}
            </article>
          );
        })}
      </div>
    </section>
  );
}

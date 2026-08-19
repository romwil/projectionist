import { monthBarPercents, recapShareText } from "../lib/yearInReview.js";

const MONTH_SHORT = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];

function PosterRow({ items, testId }) {
  const rows = Array.isArray(items) ? items.filter((item) => item?.title) : [];
  if (!rows.length) return null;
  return (
    <ul className="yir-recap-titles" data-testid={testId}>
      {rows.map((item) => (
        <li key={item.rating_key || item.title} className="yir-recap-title">
          <div className="yir-poster">
            {item.poster_url ? <img src={item.poster_url} alt="" /> : <span>{item.title}</span>}
          </div>
          <div>
            <strong>{item.title}</strong>
            {item.completions ? (
              <span className="muted">
                {" "}
                · {item.completions} finish{item.completions === 1 ? "" : "es"}
              </span>
            ) : null}
          </div>
        </li>
      ))}
    </ul>
  );
}

function Crown({ crown, kicker }) {
  if (!crown?.name) return null;
  return (
    <article className="yir-crown">
      <p className="yir-kicker">{kicker}</p>
      <p className="yir-crown-name">{crown.name}</p>
      <p className="yir-crown-count">
        {crown.count} finish{crown.count === 1 ? "" : "es"}
        {crown.runner_up?.name ? ` · then ${crown.runner_up.name}` : ""}
      </p>
    </article>
  );
}

export default function YearInReviewRecap({ recap, year, onBackToReel, onCopy, shareNote }) {
  const bars = monthBarPercents(recap?.monthly_counts);
  const hero = Array.isArray(recap?.hero) ? recap.hero : [];
  const extras = Array.isArray(recap?.extras) ? recap.extras : [];

  return (
    <section className="yir-recap" data-testid="yir-recap" aria-label={`${year} recap`}>
      <p className="yir-kicker">Your recap</p>
      <h1 className="yir-title">{recap?.headline || `Your ${year}`}</h1>

      {hero.length > 0 ? (
        <ul className="yir-hero-grid" data-testid="yir-recap-hero">
          {hero.map((item) => (
            <li key={item.id || item.label} className="yir-hero-cell">
              <span className="yir-hero-value">{item.value}</span>
              <span className="yir-hero-label">{item.label}</span>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="yir-crowns">
        <Crown crown={recap?.movie_genre} kicker="Top movie genre" />
        <Crown crown={recap?.tv_genre} kicker="Top TV genre" />
      </div>

      {recap?.top_movies?.length ? (
        <div className="yir-recap-block">
          <h2>Movies</h2>
          <PosterRow items={recap.top_movies} testId="yir-recap-movies" />
        </div>
      ) : null}

      {recap?.top_shows?.length ? (
        <div className="yir-recap-block">
          <h2>TV</h2>
          <PosterRow items={recap.top_shows} testId="yir-recap-shows" />
        </div>
      ) : null}

      {recap?.peak_month ? (
        <div className="yir-recap-block">
          <h2>{recap.peak_month.label} was busiest</h2>
          <p>
            {recap.peak_month.count} finish{recap.peak_month.count === 1 ? "" : "es"}
            {recap.peak_month.titles?.length
              ? ` · ${_join(recap.peak_month.titles.map((t) => t.title))}`
              : ""}
          </p>
        </div>
      ) : null}

      <div className="yir-month-chart" data-testid="yir-recap-months" aria-hidden="true">
        {bars.map((pct, index) => (
          <div key={MONTH_SHORT[index]} className="yir-month-col">
            <div className="yir-month-bar" style={{ height: `${Math.max(6, pct * 72)}px` }} />
            <span>{MONTH_SHORT[index]}</span>
          </div>
        ))}
      </div>

      {extras.length ? (
        <ul className="yir-extras" data-testid="yir-recap-extras">
          {extras.map((item) => (
            <li key={item.id || item.label}>
              <span className="yir-kicker">{item.label}</span>
              <strong>{item.value}</strong>
            </li>
          ))}
        </ul>
      ) : null}

      {recap?.hours_note ? <p className="yir-footnote muted">{recap.hours_note}</p> : null}
      {recap?.honesty_footnote ? (
        <p className="yir-footnote muted">{recap.honesty_footnote}</p>
      ) : null}

      <div className="yir-recap-actions">
        <button type="button" onClick={onBackToReel}>
          Back to reel
        </button>
        <button
          type="button"
          className="primary"
          data-testid="yir-copy-recap"
          onClick={() => onCopy(recapShareText(recap, year))}
        >
          Copy recap
        </button>
      </div>
      {shareNote ? <p className="muted">{shareNote}</p> : null}
    </section>
  );
}

function _join(names) {
  const clean = (names || []).filter(Boolean);
  if (!clean.length) return "";
  if (clean.length === 1) return clean[0];
  if (clean.length === 2) return `${clean[0]} and ${clean[1]}`;
  return `${clean.slice(0, -1).join(", ")}, and ${clean[clean.length - 1]}`;
}

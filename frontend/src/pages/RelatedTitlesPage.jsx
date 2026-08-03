import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { queryLibrary, walkTitleRelations } from "../api/client";
import BackLink from "../components/BackLink";
import AppShell from "../layouts/AppShell";
import { ROUTES } from "../lib/backNav.js";
import {
  RELATION_FILTERS,
  appendRelationBreadcrumb,
  filterRelationEdges,
  relationPeerSeed,
  relationSeedFromItem,
  relationSeedFromSearchParams,
  relationWhyCopy,
  relatedTitlesPath,
} from "../lib/relationUx.js";
import { titleDetailPath } from "../lib/titleLinks.js";

function RelationCard({ edge, onHop }) {
  const item = { ...(edge.peer || edge), in_library: true };
  const detailPath = titleDetailPath(item);
  const why = relationWhyCopy(edge.why);

  return (
    <article className="relation-card" data-testid="related-title-card">
      <button
        type="button"
        className="relation-card-hop"
        onClick={() => onHop(edge)}
        aria-label={`Explore connections from ${item.title}`}
      >
        <span className="relation-card-poster">
          {item.poster_url ? (
            <img src={item.poster_url} alt="" loading="lazy" />
          ) : (
            <span className="poster-fallback">{item.title?.slice(0, 1) || "?"}</span>
          )}
          <span className="relation-card-hop-label">Explore from here</span>
        </span>
      </button>
      <div className="relation-card-copy">
        <h2>
          {detailPath ? <Link to={detailPath}>{item.title}</Link> : item.title}
        </h2>
        {item.year ? <p className="relation-card-year">{item.year}</p> : null}
        <p className="relation-card-why" data-testid="related-title-why">
          {why.label}
        </p>
        {why.detail ? <p className="relation-card-surprise">{why.detail}</p> : null}
      </div>
    </article>
  );
}

function breadcrumbLabel(item) {
  const title = String(item?.title || "Title");
  return item?.year ? `${title} (${item.year})` : title;
}

export default function RelatedTitlesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialSeed = relationSeedFromSearchParams(searchParams);
  const [seed, setSeed] = useState(initialSeed);
  const [breadcrumbs, setBreadcrumbs] = useState(() => (initialSeed ? [initialSeed] : []));
  const [seedQuery, setSeedQuery] = useState(initialSeed?.title || "");
  const [seedHits, setSeedHits] = useState([]);
  const [depth, setDepth] = useState(1);
  const [filter, setFilter] = useState("all");
  const [state, setState] = useState({
    loading: Boolean(initialSeed),
    items: [],
    error: "",
    note: "",
  });

  useEffect(() => {
    const query = seedQuery.trim();
    if (query.length < 2 || query === seed?.title) {
      return undefined;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      queryLibrary({ query, limit: 8 })
        .then((data) => {
          if (!cancelled) setSeedHits(Array.isArray(data?.items) ? data.items : []);
        })
        .catch(() => {
          if (!cancelled) setSeedHits([]);
        });
    }, 220);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [seed?.title, seedQuery]);

  useEffect(() => {
    if (!seed?.item_id) return undefined;
    let cancelled = false;
    walkTitleRelations(seed.media_type, seed.item_id, {
      idType: seed.id_type,
      depth,
      limit: 50,
    })
      .then((data) => {
        if (cancelled) return;
        const items = Array.isArray(data?.items) ? data.items : [];
        setState({
          loading: false,
          items,
          error: "",
          note: items.length
            ? ""
            : "No connections are ready for this title yet. The background library refresh may still be filling them in.",
        });
      })
      .catch((error) => {
        if (cancelled) return;
        setState({
          loading: false,
          items: [],
          error: error.message || "Could not load title connections.",
          note: "",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [depth, seed]);

  const visibleEdges = useMemo(() => {
    const seen = new Set();
    return filterRelationEdges(state.items, filter).filter((edge) => {
      const key = `${edge.relation}:${edge.to_id}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [filter, state.items]);

  function selectSeed(item, { addBreadcrumb = true } = {}) {
    const next = relationSeedFromItem(item) || item;
    if (!next?.item_id) return;
    setSeed(next);
    setSeedQuery(next.title || "");
    setSeedHits([]);
    setFilter("all");
    setState({ loading: true, items: [], error: "", note: "" });
    setBreadcrumbs((current) =>
      addBreadcrumb ? appendRelationBreadcrumb(current, next) : [next],
    );
    const nextPath = relatedTitlesPath(next);
    setSearchParams(new URLSearchParams(nextPath.split("?")[1] || ""));
  }

  function handleHop(edge) {
    const next = relationPeerSeed(edge);
    if (next) selectSeed(next);
  }

  function handleBreadcrumb(item, index) {
    const next = relationSeedFromItem(item) || item;
    if (!next?.item_id) return;
    setBreadcrumbs((current) => current.slice(0, index + 1));
    setSeed(next);
    setSeedQuery(next.title || "");
    setSeedHits([]);
    setFilter("all");
    setState({ loading: true, items: [], error: "", note: "" });
    const nextPath = relatedTitlesPath(next);
    setSearchParams(new URLSearchParams(nextPath.split("?")[1] || ""));
  }

  return (
    <AppShell
      className="app-root explore-page related-titles-page"
      testId="related-titles-page"
      title="Related titles"
      eyebrow="Follow the connections — and see why they exist"
      actions={<BackLink fallbackTo={ROUTES.explore} testId="related-titles-back" />}
    >
      <main className="explore-main">
        <section className="relation-seed-panel" aria-labelledby="relation-seed-heading">
          <div>
            <h2 id="relation-seed-heading">Choose a starting title</h2>
            <p>
              Move through collection links, shared filmmakers, and plot kinship. Every card
              explains the connection.
            </p>
          </div>
          <label className="explore-seed-label" htmlFor="related-title-seed">
            Starting title
          </label>
          <input
            id="related-title-seed"
            className="explore-seed-input"
            data-testid="related-title-seed"
            type="search"
            value={seedQuery}
            placeholder="Search your library…"
            autoComplete="off"
            onChange={(event) => {
              const value = event.target.value;
              setSeedQuery(value);
              if (value.trim().length < 2) setSeedHits([]);
            }}
          />
          {seedHits.length ? (
            <ul className="explore-seed-hits" data-testid="related-title-seed-hits">
              {seedHits.map((item) => (
                <li key={item.id || item.rating_key || `${item.media_type}:${item.tmdb_id}`}>
                  <button type="button" onClick={() => selectSeed(item, { addBreadcrumb: false })}>
                    {item.title}
                    {item.year ? ` (${item.year})` : ""}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </section>

        {seed ? (
          <>
            <nav className="relation-breadcrumbs" aria-label="Connection trail">
              {breadcrumbs.map((item, index) => (
                <span key={`${item.item_id || item.library_item_id}-${index}`}>
                  {index ? <span aria-hidden="true">›</span> : null}
                  <button
                    type="button"
                    aria-current={index === breadcrumbs.length - 1 ? "page" : undefined}
                    onClick={() => handleBreadcrumb(item, index)}
                  >
                    {breadcrumbLabel(item)}
                  </button>
                </span>
              ))}
            </nav>

            <section className="relation-toolbar" aria-label="Connection filters">
              <div className="relation-filter-group">
                {RELATION_FILTERS.map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    className={`explore-media-tab${filter === option.id ? " is-active" : ""}`}
                    aria-pressed={filter === option.id}
                    onClick={() => setFilter(option.id)}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
              <label className="relation-depth">
                <span>Reach</span>
                <select
                  value={depth}
                  onChange={(event) => {
                    setDepth(Number(event.target.value) === 2 ? 2 : 1);
                    setState({ loading: true, items: [], error: "", note: "" });
                  }}
                >
                  <option value={1}>One hop</option>
                  <option value={2}>Two hops</option>
                </select>
              </label>
            </section>

            {state.loading ? <p className="status status-secondary">Following connections…</p> : null}
            {state.error || state.note ? (
              <p className={state.error ? "error" : "status status-secondary"}>
                {state.error || state.note}
              </p>
            ) : null}
            {!state.loading && !state.error && state.items.length && !visibleEdges.length ? (
              <p className="status status-secondary">
                No titles match this connection filter. Try another type or a two-hop reach.
              </p>
            ) : null}
            {visibleEdges.length ? (
              <section className="relation-grid" aria-label={`Connections from ${seed.title}`}>
                {visibleEdges.map((edge) => (
                  <RelationCard
                    key={`${edge.relation}:${edge.from_id}:${edge.to_id}`}
                    edge={edge}
                    onHop={handleHop}
                  />
                ))}
              </section>
            ) : null}
          </>
        ) : (
          <p className="relation-start-note status status-secondary">
            Pick a title to begin. Connections stay within your library.
          </p>
        )}

        <p className="explore-hub-link-row">
          <Link to={ROUTES.tags} className="app-topbar-link">
            Browse by tags instead
          </Link>
          <Link to={ROUTES.help + "#related-titles"} className="app-topbar-link">
            How connections work
          </Link>
        </p>
      </main>
    </AppShell>
  );
}

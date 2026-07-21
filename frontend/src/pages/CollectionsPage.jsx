import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getPublishedCollection, listPublishedCollections } from "../api/client";
import BackLink from "../components/BackLink";
import AppShell from "../layouts/AppShell";
import { ROUTES } from "../lib/browseLinks.js";
import { formatCollectionStepTitle, orderCollectionSteps } from "../lib/collections.js";

/**
 * Household-visible published collections and courses. Members can browse any
 * collection the owner has published; only the owner publishes (authoring lives
 * on the Lists page). Courses render as an ordered, note-annotated sequence.
 */
export default function CollectionsPage() {
  const { listId } = useParams();
  const [state, setState] = useState({ loading: true, items: [], detail: null, error: "" });

  useEffect(() => {
    let cancelled = false;
    const request = listId ? getPublishedCollection(listId) : listPublishedCollections();
    request
      .then((data) => {
        if (cancelled) return;
        setState({
          loading: false,
          items: listId ? [] : data?.items || [],
          detail: listId ? data : null,
          error: "",
        });
      })
      .catch(
        (error) =>
          !cancelled &&
          setState({
            loading: false,
            items: [],
            detail: null,
            error: error.message || "Could not load collections.",
          }),
      );
    return () => {
      cancelled = true;
    };
  }, [listId]);

  const detail = state.detail;
  const isCourse = detail?.list_kind === "course";
  const steps = orderCollectionSteps(detail?.items || []);

  return (
    <AppShell
      className="app-root collections-page"
      testId="collections-page"
      variant="browse"
      leading={<BackLink fallbackTo={listId ? "/collections" : ROUTES.explore} />}
    >
      <section className="explore-section-hero">
        <p className="person-eyebrow">{listId ? detail?.list_kind || "Collection" : "Collections"}</p>
        <h1>{listId ? detail?.name || "Collection" : "Published collections & courses"}</h1>
        <p className="explore-section-subtitle">
          {listId
            ? detail?.description ||
              (isCourse
                ? "A guided, ordered course from your curator."
                : "A curated collection from your curator.")
            : "Collections and courses your curator has published for the household."}
        </p>
      </section>

      {state.loading ? <p className="status status-secondary">Loading…</p> : null}
      {state.error ? <p className="error">{state.error}</p> : null}

      {!listId && !state.loading ? (
        state.items.length ? (
          <div className="curated-list-grid" data-testid="collections-grid">
            {state.items.map((list) => (
              <Link key={list.id} to={`/collections/${list.id}`} className="review-prompt-card">
                <strong>{list.name}</strong>
                <span>
                  {list.list_kind === "course" ? "Course" : "Collection"} · {list.item_count} title
                  {list.item_count === 1 ? "" : "s"}
                </span>
              </Link>
            ))}
          </div>
        ) : (
          <p className="explore-empty status status-secondary" data-testid="collections-empty">
            No published collections yet. When your curator publishes one, it shows up here.
          </p>
        )
      ) : null}

      {listId && !state.loading && detail ? (
        <section className="tag-results" data-testid="collection-detail">
          {steps.length ? (
            steps.map((item, index) => (
              <article
                key={item.id}
                className="collection-step"
                data-testid={`collection-step-${item.id}`}
              >
                <div className="collection-step-head">
                  {isCourse ? (
                    <span className="collection-step-index">{index + 1}</span>
                  ) : null}
                  <strong>{formatCollectionStepTitle(item)}</strong>
                </div>
                {item.note ? <p className="collection-step-note">{item.note}</p> : null}
              </article>
            ))
          ) : (
            <p className="explore-empty status status-secondary">This collection has no titles yet.</p>
          )}
        </section>
      ) : null}
    </AppShell>
  );
}

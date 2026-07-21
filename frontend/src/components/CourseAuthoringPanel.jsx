import { useEffect, useState } from "react";
import {
  setCuratedListVisibility,
  updateCuratedList,
  updateCuratedListItem,
} from "../api/client";
import {
  computeReorder,
  formatCollectionStepTitle,
  isPublished,
  orderCollectionSteps,
} from "../lib/collections.js";

/**
 * Owner authoring for collections/courses: publish to household members, mark the
 * list as an ordered "course", and add a note + reorder each step. Only the owner
 * can publish (the server enforces the role); this panel is the authoring UI.
 */
export default function CourseAuthoringPanel({ list, onRefresh }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [drafts, setDrafts] = useState({});

  useEffect(() => {
    const next = {};
    for (const item of list?.items || []) next[item.id] = item.note || "";
    setDrafts(next);
  }, [list?.id, list?.items]);

  if (!list) return null;
  const published = isPublished(list);
  const isCourse = list.list_kind === "course";
  const steps = orderCollectionSteps(list.items || []);

  async function run(fn) {
    setBusy(true);
    setError("");
    try {
      await fn();
      await onRefresh?.();
    } catch (err) {
      setError(err.message || "Could not update the collection.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="dash-panel course-authoring" data-testid="course-authoring">
      <div className="grooming-panel-head">
        <div>
          <h3 className="dash-panel-title">Publish &amp; sequence</h3>
          <p className="scheduled-task-meta">
            Publishing shares this collection with household members (read-only). Mark it a course
            to sequence steps with notes.
          </p>
        </div>
        <span
          className={`collection-visibility ${published ? "is-published" : ""}`}
          data-testid="collection-visibility"
        >
          {published ? "Published" : "Private"}
        </span>
      </div>

      {error ? <p className="dash-panel-error">{error}</p> : null}

      <div className="user-management-actions" style={{ marginBottom: "0.75rem" }}>
        <button
          type="button"
          data-testid="collection-publish-toggle"
          disabled={busy}
          onClick={() =>
            run(() => setCuratedListVisibility(list.id, published ? "private" : "published"))
          }
        >
          {published ? "Unpublish" : "Publish to members"}
        </button>
        <button
          type="button"
          className="ghost"
          data-testid="collection-kind-toggle"
          disabled={busy}
          onClick={() =>
            run(() => updateCuratedList(list.id, { list_kind: isCourse ? "list" : "course" }))
          }
        >
          {isCourse ? "Make a plain list" : "Make a course"}
        </button>
      </div>

      {isCourse ? (
        <ol className="course-step-list" data-testid="course-step-list">
          {steps.map((item, index) => (
            <li key={item.id} className="collection-step" data-testid={`course-step-${item.id}`}>
              <div className="collection-step-head">
                <span className="collection-step-index">{index + 1}</span>
                <strong>{formatCollectionStepTitle(item)}</strong>
                <span className="user-management-actions">
                  <button
                    type="button"
                    className="ghost"
                    aria-label="Move up"
                    data-testid={`course-step-up-${item.id}`}
                    disabled={busy || index === 0}
                    onClick={() =>
                      run(async () => {
                        for (const patch of computeReorder(steps, item.id, "up")) {
                          await updateCuratedListItem(list.id, patch.id, {
                            position: patch.position,
                          });
                        }
                      })
                    }
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    className="ghost"
                    aria-label="Move down"
                    data-testid={`course-step-down-${item.id}`}
                    disabled={busy || index === steps.length - 1}
                    onClick={() =>
                      run(async () => {
                        for (const patch of computeReorder(steps, item.id, "down")) {
                          await updateCuratedListItem(list.id, patch.id, {
                            position: patch.position,
                          });
                        }
                      })
                    }
                  >
                    ↓
                  </button>
                </span>
              </div>
              <textarea
                className="collection-step-note-input"
                data-testid={`course-step-note-${item.id}`}
                placeholder="Why this step, what to notice…"
                value={drafts[item.id] ?? ""}
                disabled={busy}
                onChange={(event) =>
                  setDrafts((prev) => ({ ...prev, [item.id]: event.target.value }))
                }
              />
              <div className="user-management-actions">
                <button
                  type="button"
                  className="ghost"
                  data-testid={`course-step-save-${item.id}`}
                  disabled={busy}
                  onClick={() =>
                    run(() =>
                      updateCuratedListItem(list.id, item.id, { note: drafts[item.id] ?? "" }),
                    )
                  }
                >
                  Save note
                </button>
              </div>
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  );
}

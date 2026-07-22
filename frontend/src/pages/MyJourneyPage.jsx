import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  getEngagementSummary,
  postCourseProgress,
  startCourseSyllabus,
} from "../api/client";
import AppShell from "../layouts/AppShell";
import { ROUTES, chatFromRailHref } from "../lib/backNav.js";
import {
  buildJourneyNodes,
  buildJourneyTree,
  filterJourneyNodes,
  journeyProgressSummary,
  memberFacingCopyOk,
  personaPathways,
} from "../lib/journeyAchievements.js";
import { useAuthGate } from "../components/UserMenu";

function JourneyCallout({ node, x, y, onClose }) {
  if (!node) return null;
  return (
    <div
      className="journey-callout"
      data-testid="journey-callout"
      style={{ left: x, top: y }}
      role="dialog"
      aria-label={node.displayName}
    >
      <header className="journey-callout-header">
        <strong>{node.displayName}</strong>
        <button type="button" className="ghost" aria-label="Close" onClick={onClose}>
          ✕
        </button>
      </header>
      <p>{node.displayDescription}</p>
      {node.personaId ? (
        <p className="journey-callout-meta">Persona pathway · {node.personaId}</p>
      ) : null}
      <p className="journey-callout-meta">
        {node.earned ? "Earned" : node.ready ? "Ready to pursue" : "Locked"}
        {node.tier ? ` · ${node.tier}` : ""}
      </p>
    </div>
  );
}

function JourneyDetailDrawer({ node, onClose, onChat }) {
  if (!node) return null;
  return (
    <aside className="journey-drawer" data-testid="journey-drawer" aria-label="Achievement detail">
      <header className="journey-drawer-header">
        <div>
          <p className="eyebrow">{node.ultimate ? "Ultimate badge" : "Achievement"}</p>
          <h2>{node.displayName}</h2>
        </div>
        <button type="button" className="ghost" data-testid="journey-drawer-close" onClick={onClose}>
          Close
        </button>
      </header>
      <p className="journey-drawer-body">{node.displayDescription}</p>
      <dl className="journey-drawer-meta">
        <div>
          <dt>Pathway</dt>
          <dd>{node.category}</dd>
        </div>
        <div>
          <dt>Tier</dt>
          <dd>{node.tier}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{node.earned ? "Earned" : node.locked ? "Locked" : "In progress"}</dd>
        </div>
      </dl>
      {node.personaId ? (
        <p>
          <button type="button" className="primary" onClick={() => onChat?.(node)}>
            Chat about this pathway
          </button>
        </p>
      ) : (
        <p>
          <Link to={ROUTES.chat} className="primary">
            Continue in Chat
          </Link>
        </p>
      )}
    </aside>
  );
}

export default function MyJourneyPage() {
  const { isYouth } = useAuthGate();
  const [state, setState] = useState({ loading: true, data: null, error: "" });
  const [view, setView] = useState("list");
  const [filter, setFilter] = useState("all");
  const [callout, setCallout] = useState(null);
  const [selected, setSelected] = useState(null);
  const [busyCourse, setBusyCourse] = useState("");
  const [syllabusBusy, setSyllabusBusy] = useState("");
  const [syllabusNote, setSyllabusNote] = useState("");

  function reload() {
    setState((prev) => ({ ...prev, loading: true }));
    getEngagementSummary()
      .then((data) => setState({ loading: false, data, error: "" }))
      .catch((err) =>
        setState({
          loading: false,
          data: null,
          error: err.message || "Could not load your journey.",
        }),
      );
  }

  useEffect(() => {
    reload();
  }, []);

  const nodes = useMemo(
    () => buildJourneyNodes(state.data, { isYouth }),
    [state.data, isYouth],
  );

  useEffect(() => {
    try {
      memberFacingCopyOk(nodes);
    } catch (err) {
      console.error(err);
    }
  }, [nodes]);

  const progress = useMemo(() => journeyProgressSummary(nodes), [nodes]);
  const filtered = useMemo(() => filterJourneyNodes(nodes, filter), [nodes, filter]);
  const tree = useMemo(() => buildJourneyTree(nodes), [nodes]);
  const pathways = useMemo(() => personaPathways(nodes), [nodes]);

  async function advanceCourse(course) {
    setBusyCourse(course.id);
    try {
      const nextPos = Math.min((course.position || 0) + 1, course.item_count || 0);
      const completed = nextPos >= (course.item_count || 0) && (course.item_count || 0) > 0;
      await postCourseProgress(course.id, { position: nextPos, completed });
      reload();
    } catch {
      /* keep prior state */
    } finally {
      setBusyCourse("");
    }
  }

  async function openSyllabus(course) {
    setSyllabusBusy(course.id);
    setSyllabusNote("");
    try {
      const payload = await startCourseSyllabus(course.id);
      const sessions = payload.sessions || [];
      const next = sessions.find((session) => !session.completed_at) || sessions[0];
      if (!next) {
        setSyllabusNote("No syllabus sessions yet for this course.");
        return;
      }
      const href = chatFromRailHref(
        {
          railTitle: `Syllabus · ${payload.course_name || course.name}`,
          items: [{ title: next.title, why: next.focus_note }],
        },
        { title: next.title, why: next.focus_note },
      );
      window.location.assign(href);
    } catch (err) {
      setSyllabusNote(err.message || "Could not start syllabus.");
    } finally {
      setSyllabusBusy("");
    }
  }

  function handleChatPathway(node) {
    const href = chatFromRailHref(
      { railTitle: `My Journey · ${node.displayName}` },
      { title: node.displayName, why: node.displayDescription },
    );
    window.location.assign(href);
  }

  const data = state.data;

  return (
    <AppShell
      className="app-root my-journey-page"
      testId="my-journey-page"
      title="My Journey"
      eyebrow="Cinema discovery, learning, and achievements"
    >
      <main className="explore-main journey-main">
        <section className="journey-hero" data-testid="journey-hero">
          <p className="journey-hero-lede">
            Your path into cinema and media — unlock achievements, follow persona pathways, and
            discover a few secret awards along the way.
          </p>
          <ul className="journey-progress-stats" data-testid="journey-progress-stats">
            <li>
              <strong>{progress.earned}</strong>
              <span>earned</span>
            </li>
            <li>
              <strong>{progress.inProgress}</strong>
              <span>in progress</span>
            </li>
            <li>
              <strong>
                {progress.secretsFound}/{progress.secretsTotal}
              </strong>
              <span>secrets found</span>
            </li>
          </ul>
        </section>

        <div className="journey-toolbar" data-testid="journey-toolbar">
          <div className="journey-view-toggle" role="tablist" aria-label="Journey view">
            <button
              type="button"
              role="tab"
              aria-selected={view === "list"}
              className={view === "list" ? "is-active" : ""}
              data-testid="journey-view-list"
              onClick={() => setView("list")}
            >
              List
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={view === "tree"}
              className={view === "tree" ? "is-active" : ""}
              data-testid="journey-view-tree"
              onClick={() => setView("tree")}
            >
              Achievements Tree
            </button>
          </div>
          {view === "list" ? (
            <div className="journey-filters" role="group" aria-label="Filter achievements">
              {[
                ["all", "All"],
                ["in-progress", "In progress"],
                ["earned", "Earned"],
                ["hidden", "Hidden revealed"],
              ].map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  className={filter === id ? "is-active" : ""}
                  data-testid={`journey-filter-${id}`}
                  onClick={() => setFilter(id)}
                >
                  {label}
                </button>
              ))}
            </div>
          ) : null}
        </div>

        {state.loading ? <p className="status status-secondary">Loading your journey…</p> : null}
        {state.error ? <p className="status status-error">{state.error}</p> : null}

        {!state.loading && data ? (
          <>
            {view === "list" ? (
              <section className="journey-list" data-testid="journey-list">
                <ul className="journey-card-list">
                  {filtered.map((node) => (
                    <li
                      key={node.id}
                      className={`journey-card${node.earned ? " is-earned" : ""}${node.hidden ? " is-hidden" : ""}`}
                      data-testid={`journey-node-${node.id}`}
                    >
                      <button
                        type="button"
                        className="journey-card-button"
                        onClick={() => setSelected(node)}
                      >
                        <div className="journey-card-top">
                          <strong>{node.displayName}</strong>
                          <span className="journey-tier">{node.tier}</span>
                        </div>
                        <p>{node.displayDescription}</p>
                        <div className="journey-progress-bar" aria-hidden="true">
                          <span style={{ width: `${Math.round((node.progress || 0) * 100)}%` }} />
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
                {!filtered.length ? (
                  <p className="status status-secondary">No achievements match this filter yet.</p>
                ) : null}
              </section>
            ) : (
              <section className="journey-tree" data-testid="journey-tree">
                <div className="journey-tree-grid">
                  {tree.map((column) => (
                    <div key={column.id} className="journey-tree-column" data-testid={`journey-tree-${column.id}`}>
                      <header>
                        <h2>{column.label}</h2>
                        <p className="explore-section-subtitle">Pathway toward the ultimate badge</p>
                      </header>
                      <ol className="journey-tree-nodes">
                        {column.nodes.map((node, index) => (
                          <li key={node.id}>
                            {index > 0 ? <span className="journey-tree-edge" aria-hidden="true" /> : null}
                            <button
                              type="button"
                              className={`journey-tree-node${node.earned ? " is-earned" : ""}${node.locked ? " is-locked" : ""}${node.ultimate ? " is-ultimate" : ""}`}
                              data-testid={`journey-tree-node-${node.id}`}
                              onMouseEnter={(event) => {
                                const rect = event.currentTarget.getBoundingClientRect();
                                setCallout({
                                  node,
                                  x: rect.right + 8,
                                  y: rect.top + window.scrollY,
                                });
                              }}
                              onMouseLeave={() => setCallout(null)}
                              onFocus={(event) => {
                                const rect = event.currentTarget.getBoundingClientRect();
                                setCallout({
                                  node,
                                  x: rect.right + 8,
                                  y: rect.top + window.scrollY,
                                });
                              }}
                              onBlur={() => setCallout(null)}
                              onClick={() => setSelected(node)}
                            >
                              <span className="journey-tree-node-name">{node.displayName}</span>
                              <span className="journey-tree-node-tier">{node.tier}</span>
                            </button>
                          </li>
                        ))}
                      </ol>
                    </div>
                  ))}
                </div>
                {pathways.length ? (
                  <section className="journey-persona-paths" data-testid="journey-persona-paths">
                    <h2>Persona pathways</h2>
                    <p className="explore-section-subtitle">
                      Follow a curator voice through its branch of the tree.
                    </p>
                    <ul>
                      {pathways.map((path) => (
                        <li key={path.personaId}>
                          <strong>{path.personaId}</strong>
                          {" — "}
                          {path.nodes.filter((n) => n.earned).length}/{path.nodes.length}
                          {path.completed ? " · complete" : ""}
                        </li>
                      ))}
                    </ul>
                  </section>
                ) : null}
              </section>
            )}

            {data.streak ? (
              <section className="explore-section" data-testid="journey-streak">
                <header className="explore-section-header">
                  <div>
                    <h2>Chat streak</h2>
                    <p className="explore-section-subtitle">
                      Chat days in a row: {data.streak?.current_count || 0}
                      {data.streak?.best_count ? ` · best ${data.streak.best_count}` : ""}
                      {data.session_count_30d != null
                        ? ` · ${data.session_count_30d} conversations in 30 days`
                        : ""}
                    </p>
                  </div>
                </header>
              </section>
            ) : null}

            <section className="explore-section" data-testid="journey-courses">
              <header className="explore-section-header">
                <div>
                  <h2>Cinema courses</h2>
                  <p className="explore-section-subtitle">
                    Ordered collections your curator published.{" "}
                    <Link to="/collections">Browse collections</Link>
                  </p>
                </div>
              </header>
              {(data.courses || []).length ? (
                <ul className="journey-card-list">
                  {data.courses.map((course) => (
                    <li key={course.id} className="journey-card">
                      <strong>
                        <Link to={`/collections/${course.id}`}>{course.name}</Link>
                      </strong>
                      <p>
                        Step {course.position || 0} of {course.item_count || 0}
                        {course.completed_at ? " · completed" : ""}
                      </p>
                      <div className="journey-course-actions">
                        {!course.completed_at && (course.item_count || 0) > 0 ? (
                          <button
                            type="button"
                            className="text-button"
                            disabled={busyCourse === course.id}
                            onClick={() => advanceCourse(course)}
                            data-testid={`journey-course-advance-${course.id}`}
                          >
                            Mark next step
                          </button>
                        ) : null}
                        <button
                          type="button"
                          className="text-button"
                          disabled={syllabusBusy === course.id}
                          onClick={() => openSyllabus(course)}
                          data-testid={`journey-syllabus-${course.id}`}
                        >
                          {syllabusBusy === course.id ? "Opening syllabus…" : "Open multi-session syllabus"}
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="explore-empty status status-secondary">
                  No published courses yet. When your curator publishes one, it shows up here.
                </p>
              )}
              {syllabusNote ? (
                <p className="status status-secondary" data-testid="journey-syllabus-note">
                  {syllabusNote}
                </p>
              ) : null}
            </section>

            <section className="explore-section" data-testid="journey-explainers">
              <header className="explore-section-header">
                <div>
                  <h2>Explainers</h2>
                  <p className="explore-section-subtitle">Short notes on how CuratorX habits work.</p>
                </div>
              </header>
              <ul className="journey-card-list">
                {(data.explainers || []).map((explainer) => (
                  <li key={explainer.id} className="journey-card">
                    <strong>{explainer.title}</strong>
                    <p>{explainer.body_md}</p>
                  </li>
                ))}
              </ul>
            </section>
          </>
        ) : null}

        {callout ? (
          <JourneyCallout
            node={callout.node}
            x={callout.x}
            y={callout.y}
            onClose={() => setCallout(null)}
          />
        ) : null}
        {selected ? (
          <JourneyDetailDrawer
            node={selected}
            onClose={() => setSelected(null)}
            onChat={handleChatPathway}
          />
        ) : null}
      </main>
    </AppShell>
  );
}

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getEngagementSummary, postCourseProgress, startCourseSyllabus } from "../api/client";
import AppShell from "../layouts/AppShell";
import BackLink from "../components/BackLink";
import { ROUTES, chatFromRailHref } from "../lib/backNav.js";

export default function EngagementPage() {
  const [state, setState] = useState({ loading: true, data: null, error: "" });
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
          error: err.message || "Could not load engagement.",
        }),
      );
  }

  useEffect(() => {
    reload();
  }, []);

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

  const data = state.data;

  return (
    <AppShell
      className="app-root engagement-page"
      testId="engagement-page"
      title="Engagement"
      eyebrow="Keep the habit going"
      actions={<BackLink fallbackTo={ROUTES.explore} testId="engagement-back" label="Back to Explore" />}
    >
      <main className="explore-main">
        {state.loading ? <p className="status status-secondary">Loading…</p> : null}
        {state.error ? <p className="status status-error">{state.error}</p> : null}

        {data ? (
          <>
            <section className="explore-section" data-testid="engagement-streak">
              <header className="explore-section-header">
                <div>
                  <h2>Streak</h2>
                  <p className="explore-section-subtitle">
                    Chat days in a row: {data.streak?.current_count || 0}
                    {data.streak?.best_count
                      ? ` · best ${data.streak.best_count}`
                      : ""}
                    {data.session_count_30d != null
                      ? ` · ${data.session_count_30d} conversations in 30 days`
                      : ""}
                  </p>
                </div>
              </header>
            </section>

            <section className="explore-section" data-testid="engagement-challenges">
              <header className="explore-section-header">
                <div>
                  <h2>Challenges</h2>
                  <p className="explore-section-subtitle">Rate titles to tune your taste and earn badges.</p>
                </div>
              </header>
              <ul className="engagement-card-list">
                {(data.challenges || []).map((challenge) => (
                  <li key={challenge.id} className="engagement-card">
                    <strong>{challenge.title}</strong>
                    <p>{challenge.description}</p>
                    <span className="status status-secondary">
                      {challenge.progress || 0} / {challenge.target_count}
                      {challenge.completed_at ? " · done" : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </section>

            <section className="explore-section" data-testid="engagement-badges">
              <header className="explore-section-header">
                <div>
                  <h2>Badges</h2>
                  <p className="explore-section-subtitle">Milestones you have unlocked.</p>
                </div>
              </header>
              {(data.badges || []).length ? (
                <ul className="engagement-card-list">
                  {data.badges.map((badge) => (
                    <li key={badge.id} className="engagement-card">
                      <strong>{badge.name}</strong>
                      <p>{badge.description}</p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="explore-empty status status-secondary">No badges yet — rate a title to start.</p>
              )}
            </section>

            <section className="explore-section" data-testid="engagement-courses">
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
                <ul className="engagement-card-list">
                  {data.courses.map((course) => (
                    <li key={course.id} className="engagement-card">
                      <strong>
                        <Link to={`/collections/${course.id}`}>{course.name}</Link>
                      </strong>
                      <p>
                        Step {course.position || 0} of {course.item_count || 0}
                        {course.completed_at ? " · completed" : ""}
                      </p>
                      <div className="engagement-course-actions">
                        {!course.completed_at && (course.item_count || 0) > 0 ? (
                          <button
                            type="button"
                            className="text-button"
                            disabled={busyCourse === course.id}
                            onClick={() => advanceCourse(course)}
                            data-testid={`engagement-course-advance-${course.id}`}
                          >
                            Mark next step
                          </button>
                        ) : null}
                        <button
                          type="button"
                          className="text-button"
                          disabled={syllabusBusy === course.id}
                          onClick={() => openSyllabus(course)}
                          data-testid={`engagement-syllabus-${course.id}`}
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
                <p className="status status-secondary" data-testid="engagement-syllabus-note">
                  {syllabusNote}
                </p>
              ) : null}
            </section>

            <section className="explore-section" data-testid="engagement-explainers">
              <header className="explore-section-header">
                <div>
                  <h2>Explainers</h2>
                  <p className="explore-section-subtitle">Short notes on how CuratorX habits work.</p>
                </div>
              </header>
              <ul className="engagement-card-list">
                {(data.explainers || []).map((explainer) => (
                  <li key={explainer.id} className="engagement-card">
                    <strong>{explainer.title}</strong>
                    <p>{explainer.body_md}</p>
                  </li>
                ))}
              </ul>
            </section>
          </>
        ) : null}
      </main>
    </AppShell>
  );
}

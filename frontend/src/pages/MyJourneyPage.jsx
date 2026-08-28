import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import {
  confirmAction,
  getJourneyExploration,
  startCourseSyllabus,
  syllabusPublishHandoff,
} from "../api/client";
import ChamberEmpty from "../components/ChamberEmpty";
import { useAuthGate } from "../components/UserMenu";
import AppShell from "../layouts/AppShell";
import { ROUTES, chatFromRailHref } from "../lib/backNav.js";
import {
  JOURNEY_EYEBROW,
  JOURNEY_HERO_LEDE,
  YOUTH_JOURNEY_EYEBROW,
  YOUTH_JOURNEY_HERO_LEDE,
  hasExplorationContent,
  insightBrowseHref,
  insightChatHref,
  personChatHref,
  personExploreHref,
  personShelfLabel,
} from "../lib/journeyExploration.js";
import { guestDeepLinkBlocked } from "../lib/memberShell.js";

const PEOPLE_RAILS = [
  { id: "directors", title: "Directors in your shelf", subtitle: "Voices behind the films you keep returning to." },
  {
    id: "cinematographers",
    title: "Cinematographers",
    subtitle: "Light, lens, and frame — craft across your collection.",
  },
  {
    id: "composers",
    title: "Composers",
    subtitle: "Scores and soundtracks woven through your library.",
  },
];

function JourneyPersonCard({ person }) {
  const exploreHref = personExploreHref(person);
  const chatHref = personChatHref(person);
  const shelf = personShelfLabel(person);
  const initial = String(person?.name || "?").slice(0, 1);

  return (
    <li className="journey-person-card" data-testid={`journey-person-${person.role}-${person.name}`}>
      <div className="journey-person-card-main">
        {person.profile_url ? (
          <img src={person.profile_url} alt="" className="journey-person-avatar" loading="lazy" />
        ) : (
          <span className="journey-person-avatar journey-person-avatar--fallback" aria-hidden="true">
            {initial}
          </span>
        )}
        <div>
          {exploreHref ? (
            <Link to={exploreHref} className="journey-person-name">
              {person.name}
            </Link>
          ) : (
            <strong className="journey-person-name">{person.name}</strong>
          )}
          {shelf ? <p className="journey-person-meta">{shelf}</p> : null}
        </div>
      </div>
      {chatHref ? (
        <Link to={chatHref} className="text-button journey-person-chat" data-testid={`journey-person-chat-${person.name}`}>
          Explore in Chat
        </Link>
      ) : null}
    </li>
  );
}

function JourneyPeopleRail({ railId, title, subtitle, people = [] }) {
  if (!people.length) return null;
  return (
    <section className="explore-section" data-testid={`journey-people-${railId}`}>
      <header className="explore-section-header">
        <div>
          <h2>{title}</h2>
          <p className="explore-section-subtitle">{subtitle}</p>
        </div>
      </header>
      <ul className="journey-person-list">
        {people.map((person) => (
          <JourneyPersonCard key={`${person.role}-${person.name}`} person={person} />
        ))}
      </ul>
    </section>
  );
}

function JourneyInsightCard({ insight }) {
  const browseHref = insightBrowseHref(insight);
  const chatHref = insightChatHref(insight);

  return (
    <li className="journey-insight-card" data-testid={`journey-insight-${insight.id}`}>
      <p className="journey-insight-kind">{insight.kind === "era" ? "Era" : "Genre"}</p>
      <strong>{insight.label}</strong>
      <p className="journey-insight-note">{insight.note}</p>
      <div className="journey-insight-actions">
        {browseHref ? (
          <Link to={browseHref} className="text-button">
            Browse shelf
          </Link>
        ) : null}
        {chatHref ? (
          <Link to={chatHref} className="text-button" data-testid={`journey-insight-chat-${insight.id}`}>
            Explore in Chat
          </Link>
        ) : null}
      </div>
    </li>
  );
}

export default function MyJourneyPage() {
  const { authReady, isYouth, role, multiUserEnabled, isOwner } = useAuthGate();
  const [publishBusy, setPublishBusy] = useState("");
  const [state, setState] = useState({ loading: true, data: null, error: "" });
  const [syllabusBusy, setSyllabusBusy] = useState("");
  const [syllabusNote, setSyllabusNote] = useState("");

  function reload() {
    setState((prev) => ({ ...prev, loading: true }));
    getJourneyExploration()
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
    if (!authReady || guestDeepLinkBlocked({ role, multiUserEnabled, authReady })) return;
    reload();
  }, [authReady, role, multiUserEnabled]);

  if (!authReady) {
    return (
      <div className="app-root app-loading" data-testid="my-journey-auth-loading">
        <p className="login-lede">Loading…</p>
      </div>
    );
  }

  if (guestDeepLinkBlocked({ role, multiUserEnabled, authReady: true })) {
    return <Navigate to={ROUTES.explore} replace />;
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

  async function publishSyllabusToPlex(course) {
    setPublishBusy(course.id);
    setSyllabusNote("");
    try {
      const preview = await syllabusPublishHandoff(course.id, { confirm: false, target: "plex" });
      if (preview?.needs_confirm) {
        const ok = window.confirm(preview.message || `Publish “${course.name}” to Plex?`);
        if (!ok) return;
      }
      const result = await syllabusPublishHandoff(course.id, { confirm: true, target: "plex" });
      if (result?.confirmation_token) {
        await confirmAction(result.confirmation_token, true);
        setSyllabusNote(result.message || `Published “${course.name}” to Plex.`);
      } else {
        setSyllabusNote(result.message || "Publish queued.");
      }
    } catch (err) {
      setSyllabusNote(err.message || "Could not publish syllabus collection.");
    } finally {
      setPublishBusy("");
    }
  }

  const data = state.data;
  const eyebrow = isYouth ? YOUTH_JOURNEY_EYEBROW : JOURNEY_EYEBROW;
  const heroLede = isYouth ? YOUTH_JOURNEY_HERO_LEDE : JOURNEY_HERO_LEDE;
  const showPeopleRails = !isYouth;
  const showInsights = !isYouth;

  return (
    <AppShell
      className="app-root my-journey-page"
      testId="my-journey-page"
      title="My Journey"
      eyebrow={eyebrow}
    >
      <main className="explore-main journey-main">
        <section className="journey-hero" data-testid="journey-hero">
          <p className="journey-hero-lede">{heroLede}</p>
        </section>

        {state.loading ? <p className="status status-secondary">Loading your cinema map…</p> : null}
        {state.error ? <p className="status status-error">{state.error}</p> : null}

        {!state.loading && data ? (
          <>
            {showPeopleRails
              ? PEOPLE_RAILS.map((rail) => (
                  <JourneyPeopleRail
                    key={rail.id}
                    railId={rail.id}
                    title={rail.title}
                    subtitle={rail.subtitle}
                    people={data.people?.[rail.id] || []}
                  />
                ))
              : null}

            {showInsights && (data.insights || []).length ? (
              <section className="explore-section" data-testid="journey-insights">
                <header className="explore-section-header">
                  <div>
                    <h2>Threads in your collection</h2>
                    <p className="explore-section-subtitle">
                      Genres and eras that show up often — editorial notes, not scores.
                    </p>
                  </div>
                </header>
                <ul className="journey-insight-list">
                  {(data.insights || []).map((insight) => (
                    <JourneyInsightCard key={insight.id} insight={insight} />
                  ))}
                </ul>
              </section>
            ) : null}

            <section className="explore-section" data-testid="journey-courses">
              <header className="explore-section-header">
                <div>
                  <h2>Curated viewing paths</h2>
                  <p className="explore-section-subtitle">
                    Ordered collections from your curator.{" "}
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
                      {course.description ? <p>{course.description}</p> : null}
                      <p className="journey-course-meta">
                        {course.item_count || 0} title{(course.item_count || 0) === 1 ? "" : "s"}
                      </p>
                      <div className="journey-course-actions">
                        <Link to={`/collections/${course.id}`} className="text-button">
                          Open collection
                        </Link>
                        <button
                          type="button"
                          className="text-button"
                          disabled={syllabusBusy === course.id}
                          onClick={() => openSyllabus(course)}
                          data-testid={`journey-syllabus-${course.id}`}
                        >
                          {syllabusBusy === course.id ? "Opening syllabus…" : "Open multi-session syllabus"}
                        </button>
                        {isOwner ? (
                          <button
                            type="button"
                            className="text-button"
                            disabled={publishBusy === course.id}
                            onClick={() => publishSyllabusToPlex(course)}
                            data-testid={`journey-syllabus-publish-${course.id}`}
                          >
                            {publishBusy === course.id ? "Publishing…" : "Publish syllabus to Plex"}
                          </button>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <ChamberEmpty
                  title="No curated paths yet"
                  body="When your curator publishes a cinema course, it shows up here as a viewing path."
                  ctaLabel="Browse collections"
                  ctaTo="/collections"
                  testId="journey-courses-empty"
                />
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
                  <p className="explore-section-subtitle">Short notes on how Projectionist habits work.</p>
                </div>
              </header>
              {(data.explainers || []).length ? (
                <ul className="journey-card-list">
                  {(data.explainers || []).map((explainer) => (
                    <li key={explainer.id} className="journey-card">
                      <strong>{explainer.title}</strong>
                      <p>{explainer.body_md}</p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="status status-secondary">No explainers yet.</p>
              )}
            </section>

            {!hasExplorationContent(data) ? (
              <ChamberEmpty
                title="Your map is still filling in"
                body="Watch, rate, and chat about titles — directors and craft threads appear as your library grows."
                ctaLabel="Explore your shelf"
                ctaTo={ROUTES.explore}
                testId="journey-exploration-empty"
              />
            ) : null}
          </>
        ) : null}
      </main>
    </AppShell>
  );
}

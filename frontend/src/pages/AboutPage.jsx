import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getHealth } from "../api/client";
import BackLink from "../components/BackLink";
import ReleaseNotesPanel from "../components/ReleaseNotesPanel";
import AppShell from "../layouts/AppShell";
import { ROUTES } from "../lib/backNav.js";
import { fetchReleaseNotes, normalizeReleaseNotes } from "../lib/releaseNotes.js";

const GITHUB_URL = "https://github.com/romwil/curatorx";
const DOCKER_HUB_URL = "https://hub.docker.com/r/romwil/curatorx";
const DOCS_URL = `${GITHUB_URL}/tree/main/docs`;

export default function AboutPage() {
  const [version, setVersion] = useState("");
  const [releases, setReleases] = useState([]);
  const [notesError, setNotesError] = useState("");
  const [notesLoading, setNotesLoading] = useState(true);

  useEffect(() => {
    getHealth()
      .then((data) => setVersion(data?.version || ""))
      .catch(() => setVersion(""));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setNotesLoading(true);
    fetchReleaseNotes()
      .then((payload) => {
        if (cancelled) return;
        setReleases(normalizeReleaseNotes(payload));
        setNotesError("");
        setNotesLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setReleases([]);
        setNotesError("Could not load release notes.");
        setNotesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const eyebrow = version ? `Version ${version}` : "Private cinema companion";

  return (
    <AppShell
      className="app-root explore-page about-page"
      testId="about-page"
      requireAuth={false}
      title="About"
      eyebrow={eyebrow}
      actions={<BackLink fallbackTo={ROUTES.chat} testId="about-back" label="Back to chat" />}
    >
      <main className="explore-main about-main">
        <section className="explore-section about-intro" aria-labelledby="about-intro-heading">
          <div className="explore-section-header">
            <h2 id="about-intro-heading">The story</h2>
          </div>
          <p className="about-lede">
            A private cinema companion for your Plex and *arr stack — opinions in chat, taste in the
            library, credentials that stay home.
          </p>
          <p>
            CuratorX grew out of living with a big personal library and wanting a curator who knew it —
            not another remote catalog that forgets where your files live. It indexes what you already
            own, learns from how you rate and refuse titles, and talks like the friend you want in the
            aisle.
          </p>
          <p>
            Owners configure the stack once. Household members sign in with Plex. Nobody has to pretend
            this is a SaaS marketing site.
          </p>
          {version ? (
            <p className="status status-secondary" data-testid="about-version">
              Running {version}
              {" · "}
              <a href="#release-notes" className="about-whats-new-link" data-testid="about-whats-new-link">
                What’s new
              </a>
            </p>
          ) : null}
        </section>

        <section
          className="explore-section about-release-notes"
          id="release-notes"
          aria-labelledby="about-release-notes-heading"
        >
          <div className="explore-section-header">
            <h2 id="about-release-notes-heading">Release notes</h2>
          </div>
          <p className="status status-secondary about-section-meta">
            Full history from CHANGELOG — newest first.
          </p>
          {notesError ? (
            <p className="error" data-testid="about-release-notes-error">
              {notesError}
            </p>
          ) : notesLoading ? (
            <p className="status status-secondary" data-testid="about-release-notes-loading">
              Loading release notes…
            </p>
          ) : (
            <ReleaseNotesPanel
              releases={releases}
              showJumpLinks
              scrollable
              testId="about-release-notes"
            />
          )}
        </section>

        <section className="explore-section" aria-labelledby="about-links-heading">
          <div className="explore-section-header">
            <h2 id="about-links-heading">Links</h2>
          </div>
          <ul className="about-links">
            <li>
              <a href={GITHUB_URL} target="_blank" rel="noreferrer">
                GitHub
              </a>
            </li>
            <li>
              <a href={DOCS_URL} target="_blank" rel="noreferrer">
                Documentation
              </a>
            </li>
            <li>
              <a href={DOCKER_HUB_URL} target="_blank" rel="noreferrer">
                Docker Hub · romwil/curatorx
              </a>
            </li>
            <li>
              <Link to="/help">Help</Link>
            </li>
            <li>
              <Link to="/privacy">Privacy &amp; data use</Link>
            </li>
            <li>
              <a href={`${GITHUB_URL}/blob/main/LICENSE`} target="_blank" rel="noreferrer">
                License · MIT
              </a>
            </li>
          </ul>
        </section>
      </main>
    </AppShell>
  );
}

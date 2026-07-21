import { useRef } from "react";
import { plainChangelogText } from "../lib/releaseNotes.js";

/**
 * Renders one or more changelog releases.
 * @param {{
 *   releases: Array<{
 *     version: string,
 *     date?: string,
 *     summary?: string,
 *     highlights?: string[],
 *     sections?: Array<{ title: string, bullets?: string[] }>,
 *   }>,
 *   showJumpLinks?: boolean,
 *   scrollable?: boolean,
 *   preferHighlights?: boolean,
 *   testId?: string,
 * }} props
 *
 * `preferHighlights` (used by the What's New modal) leads with the benefit-led
 * "Highlights" copy and hides the technical sections when highlights exist.
 * The About page leaves it off, so it shows highlights *and* the full detail.
 */
export default function ReleaseNotesPanel({
  releases = [],
  showJumpLinks = false,
  scrollable = false,
  preferHighlights = false,
  testId = "release-notes-panel",
}) {
  const panelRef = useRef(null);

  if (!releases.length) {
    return (
      <p className="status status-secondary" data-testid={`${testId}-empty`}>
        Release notes are not available yet.
      </p>
    );
  }

  function jumpToVersion(event, version) {
    event.preventDefault();
    const target = panelRef.current?.querySelector(`#release-${CSS.escape(version)}`);
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    if (typeof window !== "undefined" && window.history?.replaceState) {
      window.history.replaceState(null, "", `#release-${version}`);
    }
  }

  return (
    <div
      ref={panelRef}
      className={`release-notes-panel${scrollable ? " is-scrollable" : ""}`}
      data-testid={testId}
    >
      {showJumpLinks && releases.length > 1 ? (
        <nav className="release-notes-jumps" aria-label="Release versions" data-testid={`${testId}-jumps`}>
          {releases.map((release) => (
            <a
              key={release.version}
              href={`#release-${release.version}`}
              onClick={(event) => jumpToVersion(event, release.version)}
            >
              {release.version}
            </a>
          ))}
        </nav>
      ) : null}

      {releases.map((release) => (
        <article
          key={release.version}
          id={`release-${release.version}`}
          className="release-notes-version"
          data-testid={`${testId}-version-${release.version}`}
        >
          <header className="release-notes-version-header">
            <h3>{release.version}</h3>
            {release.date ? <time dateTime={release.date}>{release.date}</time> : null}
          </header>
          {release.summary ? <p className="release-notes-summary">{release.summary}</p> : null}
          {(release.highlights || []).length ? (
            <div className="release-notes-section release-notes-highlights">
              <h4>Highlights</h4>
              <ul>
                {release.highlights.map((bullet) => (
                  <li key={bullet}>{plainChangelogText(bullet)}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {(preferHighlights && (release.highlights || []).length
            ? []
            : release.sections || []
          ).map((section) => (
            <div key={`${release.version}-${section.title}`} className="release-notes-section">
              <h4>{section.title}</h4>
              <ul>
                {(section.bullets || []).map((bullet) => (
                  <li key={bullet}>{plainChangelogText(bullet)}</li>
                ))}
              </ul>
            </div>
          ))}
        </article>
      ))}
    </div>
  );
}

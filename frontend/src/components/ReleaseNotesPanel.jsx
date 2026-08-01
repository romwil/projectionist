import { useRef } from "react";
import { allocateReleaseVersionJumps, plainChangelogText } from "../lib/releaseNotes.js";

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
  const jumps = allocateReleaseVersionJumps(releases);

  if (!releases.length) {
    return (
      <p className="status status-secondary" data-testid={`${testId}-empty`}>
        Release notes are not available yet.
      </p>
    );
  }

  function jumpToVersion(version, event) {
    event?.preventDefault?.();
    const targetVersion = String(version || "").trim();
    if (!targetVersion) return;
    const target = panelRef.current?.querySelector(`#release-${CSS.escape(targetVersion)}`);
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    if (typeof window !== "undefined" && window.history?.replaceState) {
      window.history.replaceState(null, "", `#release-${targetVersion}`);
    }
  }

  return (
    <div
      ref={panelRef}
      className={`release-notes-panel${scrollable ? " is-scrollable" : ""}`}
      data-testid={testId}
    >
      {showJumpLinks && jumps.all.length > 1 ? (
        <nav
          className={`release-notes-jumps${jumps.mode === "picker" ? " is-compact" : ""}`}
          aria-label="Release versions"
          data-testid={`${testId}-jumps`}
          data-mode={jumps.mode}
        >
          {jumps.mode === "picker" ? (
            <label className="release-notes-jump-picker">
              <span className="release-notes-jump-picker-label">Jump to</span>
              <select
                className="release-notes-jump-select"
                data-testid={`${testId}-jump-select`}
                defaultValue=""
                aria-label="Jump to release version"
                onChange={(event) => {
                  const next = event.target.value;
                  if (next) jumpToVersion(next, event);
                }}
              >
                <option value="" disabled>
                  Version…
                </option>
                {jumps.all.map((version) => (
                  <option key={version} value={version}>
                    {version}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <div className="release-notes-jump-chips" data-testid={`${testId}-jump-chips`}>
            {jumps.recent.map((version) => (
              <a
                key={version}
                className="release-notes-jump-chip"
                href={`#release-${version}`}
                onClick={(event) => jumpToVersion(version, event)}
              >
                {version}
              </a>
            ))}
          </div>
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

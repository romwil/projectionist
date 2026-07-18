import { watchProgressLabel, watchProgressState } from "../lib/watchProgress.js";

/**
 * Plex-like upper-right watch overlay for any poster surface.
 * Full watched → checkmark; partial → distinct in-progress glyph.
 */
export default function WatchProgressBadge({ item, className = "" }) {
  const state = watchProgressState(item);
  if (state === "unwatched") return null;

  const label = watchProgressLabel(state);
  const icon = state === "watched" ? "check" : "timelapse";

  return (
    <span
      className={`watch-progress-badge is-${state}${className ? ` ${className}` : ""}`}
      data-testid="watch-progress-badge"
      data-state={state}
      aria-label={label}
      title={label}
    >
      <span className="material-symbols-outlined" aria-hidden="true">
        {icon}
      </span>
    </span>
  );
}

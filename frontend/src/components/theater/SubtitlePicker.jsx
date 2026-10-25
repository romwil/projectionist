import {
  formatSubtitleDelay,
  stepSubtitleDelay,
  SUBTITLE_BURN_IN_NOTE,
  SUBTITLE_DELAY_STEP_SEC,
} from "../../lib/subtitleCues.js";

/**
 * One CC menu for every player. Off + drawable text tracks, then last-resort
 * Plex burn-in chips. Bitmap streams are never overlay options.
 */
export default function SubtitlePicker({
  tracks = [],
  burnInTracks = [],
  activeId = -1,
  onSelect,
  state = "idle",
  error = "",
  note = "",
  emptyMessage = "",
  delaySec = 0,
  onDelayChange,
  className = "",
  testId = "subtitle-picker",
  leading = null,
  trailing = null,
}) {
  const pickable = tracks.filter((track) => track.renderable !== false && !track.burnIn);
  const burnIn = Array.isArray(burnInTracks) ? burnInTracks : [];
  const burnInActive = Boolean(burnIn.find((track) => track.index === activeId));
  const showSync = activeId !== -1 && !burnInActive && typeof onDelayChange === "function";
  const hasChoices = pickable.length + burnIn.length > 0;
  const burnInNote = burnIn.length ? SUBTITLE_BURN_IN_NOTE : "";
  return (
    <div className={`live-cc-picker subtitle-picker ${className}`.trim()} data-testid={testId} data-theater-chrome="true">
      <button
        type="button"
        className={`ghost live-cc-option${activeId === -1 ? " is-active" : ""}`}
        onClick={() => onSelect?.({ index: -1 })}
        data-testid={`${testId}-off`}
      >
        Off
      </button>
      {leading}
      {pickable.map((track) => (
        <button
          key={track.index}
          type="button"
          className={`ghost live-cc-option${activeId === track.index ? " is-active" : ""}`}
          onClick={() => onSelect?.(track)}
          data-testid={`${testId}-track`}
        >
          {track.label}
        </button>
      ))}
      {burnIn.map((track) => (
        <button
          key={track.index}
          type="button"
          className={`ghost live-cc-option${activeId === track.index ? " is-active" : ""}`}
          onClick={() => onSelect?.(track)}
          data-testid={`${testId}-burn-in`}
        >
          {track.label}
        </button>
      ))}
      {showSync ? (
        <span className="subtitle-sync" data-testid={`${testId}-sync`}>
          <button
            type="button"
            className="ghost live-cc-option"
            onClick={() => onDelayChange(stepSubtitleDelay(delaySec, -SUBTITLE_DELAY_STEP_SEC))}
            aria-label="Show subtitles earlier"
            data-testid={`${testId}-sync-earlier`}
          >
            ◂
          </button>
          <span className="subtitle-sync-value">{formatSubtitleDelay(delaySec)}</span>
          <button
            type="button"
            className="ghost live-cc-option"
            onClick={() => onDelayChange(stepSubtitleDelay(delaySec, SUBTITLE_DELAY_STEP_SEC))}
            aria-label="Show subtitles later"
            data-testid={`${testId}-sync-later`}
          >
            ▸
          </button>
        </span>
      ) : null}
      {state === "loading" ? (
        <p className="live-cc-empty" data-testid={`${testId}-loading`}>Loading subtitles…</p>
      ) : null}
      {state === "error" && error ? (
        <p className="live-cc-empty" role="alert" data-testid={`${testId}-error`}>{error}</p>
      ) : null}
      {!hasChoices && emptyMessage ? (
        <p className="live-cc-empty" data-testid={`${testId}-empty`}>{emptyMessage}</p>
      ) : null}
      {note ? (
        <p className="live-cc-empty" data-testid={`${testId}-note`}>{note}</p>
      ) : null}
      {burnInNote && note !== burnInNote ? (
        <p className="live-cc-empty" data-testid={`${testId}-burn-in-note`}>
          {burnInNote}
        </p>
      ) : null}
      {trailing}
    </div>
  );
}

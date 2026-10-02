import { formatSubtitleDelay, SUBTITLE_DELAY_STEP_SEC } from "../../lib/subtitleCues.js";

/**
 * One CC menu for every player. Off + real tracks; unreadable tracks stay
 * listed (disabled) with the honest reason. `extraOptions` lets Live add its
 * in-stream HLS tracks and the "Ask Plex" action.
 */
export default function SubtitlePicker({
  tracks = [],
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
  const showSync = activeId !== -1 && typeof onDelayChange === "function";
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
      {tracks.map((track) => (
        <button
          key={track.index}
          type="button"
          className={`ghost live-cc-option${activeId === track.index ? " is-active" : ""}`}
          disabled={!track.renderable}
          title={track.renderable ? undefined : track.unavailableReason}
          onClick={() => onSelect?.(track)}
          data-testid={`${testId}-track`}
        >
          {track.label}
          {track.renderable ? "" : " · can’t draw"}
        </button>
      ))}
      {showSync ? (
        <span className="subtitle-sync" data-testid={`${testId}-sync`}>
          <button type="button" className="ghost live-cc-option" onClick={() => onDelayChange(delaySec - SUBTITLE_DELAY_STEP_SEC)} aria-label="Show subtitles earlier">
            ◂
          </button>
          <span className="subtitle-sync-value">{formatSubtitleDelay(delaySec)}</span>
          <button type="button" className="ghost live-cc-option" onClick={() => onDelayChange(delaySec + SUBTITLE_DELAY_STEP_SEC)} aria-label="Show subtitles later">
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
      {!tracks.length && emptyMessage ? (
        <p className="live-cc-empty" data-testid={`${testId}-empty`}>{emptyMessage}</p>
      ) : null}
      {note ? (
        <p className="live-cc-empty" data-testid={`${testId}-note`}>{note}</p>
      ) : null}
      {trailing}
    </div>
  );
}

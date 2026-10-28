import {
  POP_OUT_OF_WINDOW_LABEL,
  SHRINK_ONTO_PAGE_LABEL,
} from "../../lib/inAppPip.js";
import {
  SCRUB_MAX,
  SKIP_LONG_SECONDS,
  SKIP_SECONDS,
  formatClockMs,
} from "../../lib/theaterPlayer.js";
import { playFrameMenuLabel } from "../../lib/uiPrefs.js";
import { clampSubtitleDelay } from "../../lib/subtitleCues.js";
import SubtitlePicker from "./SubtitlePicker.jsx";

/**
 * Library Play transport chrome. Session / resume / CW stay in LibraryPlayer.
 */
export default function LibraryPlayerOsd({
  popout = false,
  headline = "Play",
  metaLine = "",
  nowMs = 0,
  durationMs = 0,
  bufferedPct = 0,
  sliderPct = 0,
  longSkip = false,
  playing = false,
  ccOpen = false,
  moreOpen = false,
  barActions = {},
  closePlace = {},
  pipSupported = false,
  plexHref = "",
  blackFrame = false,
  subTracks = [],
  burnInTracks = [],
  activeSub = -1,
  activeSubTrack = null,
  subs = {},
  subListNote = "",
  subDelay = 0,
  activeBurnIn = false,
  onSkipBy,
  onTogglePlayback,
  onBeginScrub,
  onEndScrub,
  onScrubInput,
  onToggleCc,
  onShrink,
  onFullscreen,
  onLeaveWatch,
  onToggleMore,
  onCloseMore,
  onEnterPiP,
  onOpenPopout,
  onToggleBlackFrame,
  onSelectSubtitle,
  onDelayChange,
}) {
  return (
    <div className="theater-osd-inner" data-testid="library-osd-inner">
      <div className="theater-osd-meta">
        {popout ? <p className="theater-osd-kicker">Pop-out</p> : null}
        <h2 className="theater-osd-title">{headline}</h2>
        {metaLine ? <p className="theater-osd-episode">{metaLine}</p> : null}
      </div>

      <div className="theater-scrubber-row" data-testid="library-scrubber-row">
        <span className="theater-clock">{formatClockMs(nowMs)}</span>
        <label className="theater-scrubber" data-theater-chrome="true">
          <span className="visually-hidden">Seek</span>
          <span
            className="theater-scrubber-buffered"
            style={{ width: `${Math.max(0, Math.min(100, bufferedPct))}%` }}
          />
          <input
            type="range"
            min={0}
            max={SCRUB_MAX}
            step={1}
            value={Math.max(0, Math.min(SCRUB_MAX, sliderPct))}
            aria-label="Seek"
            aria-valuetext={formatClockMs(nowMs)}
            onPointerDown={onBeginScrub}
            onPointerUp={onEndScrub}
            onPointerCancel={onEndScrub}
            onChange={onScrubInput}
          />
        </label>
        <span className="theater-clock">{durationMs ? formatClockMs(durationMs) : "–:––"}</span>
      </div>

      <div className="theater-osd-transport" data-testid="library-osd-transport">
        {longSkip ? (
          <button
            type="button"
            className="theater-osd-skip theater-osd-skip-long"
            onClick={() => onSkipBy(-SKIP_LONG_SECONDS)}
            aria-label={`Skip back ${SKIP_LONG_SECONDS} seconds`}
            data-testid="library-skip-back-30"
          >
            −{SKIP_LONG_SECONDS}
          </button>
        ) : null}
        <button
          type="button"
          className="theater-osd-skip"
          onClick={() => onSkipBy(-SKIP_SECONDS)}
          aria-label={`Skip back ${SKIP_SECONDS} seconds`}
          data-testid="library-skip-back"
        >
          −{SKIP_SECONDS}
        </button>
        <button
          type="button"
          className="theater-osd-play"
          onClick={onTogglePlayback}
          aria-label={playing ? "Pause" : "Play"}
          data-testid="library-play-toggle"
        >
          <span className="theater-osd-play-glyph" aria-hidden="true">
            {playing ? "❚❚" : "▶"}
          </span>
          <span className="theater-osd-play-label">{playing ? "Pause" : "Play"}</span>
        </button>
        <button
          type="button"
          className="theater-osd-skip"
          onClick={() => onSkipBy(SKIP_SECONDS)}
          aria-label={`Skip forward ${SKIP_SECONDS} seconds`}
          data-testid="library-skip-forward"
        >
          +{SKIP_SECONDS}
        </button>
        {longSkip ? (
          <button
            type="button"
            className="theater-osd-skip theater-osd-skip-long"
            onClick={() => onSkipBy(SKIP_LONG_SECONDS)}
            aria-label={`Skip forward ${SKIP_LONG_SECONDS} seconds`}
            data-testid="library-skip-forward-30"
          >
            +{SKIP_LONG_SECONDS}
          </button>
        ) : null}

        <span className="theater-osd-spacer" aria-hidden="true" />

        <button
          type="button"
          className={`theater-osd-secondary${ccOpen ? " is-active" : ""}`}
          onClick={onToggleCc}
          aria-expanded={ccOpen}
          data-testid="library-cc"
        >
          CC
        </button>
        {barActions.shrinkOntoPage ? (
          <button
            type="button"
            className="theater-osd-secondary library-shrink"
            onClick={onShrink}
            data-testid="library-shrink"
            aria-label={SHRINK_ONTO_PAGE_LABEL}
          >
            <span className="library-shrink-short">Shrink</span>
            <span className="library-shrink-long"> onto page</span>
          </button>
        ) : null}
        <button
          type="button"
          className="theater-osd-secondary"
          onClick={onFullscreen}
          data-testid="library-fullscreen"
        >
          Fullscreen
        </button>
        {closePlace.onBar ? (
          <button
            type="button"
            className="theater-osd-secondary"
            onClick={onLeaveWatch}
            data-testid="library-close"
          >
            {closePlace.label}
          </button>
        ) : null}
        <div className="theater-osd-more-wrap" data-theater-chrome="true">
          <button
            type="button"
            className={`theater-osd-secondary${moreOpen ? " is-active" : ""}`}
            onClick={onToggleMore}
            aria-expanded={moreOpen}
            aria-haspopup="menu"
            data-testid="library-osd-more"
          >
            More
          </button>
          {moreOpen ? (
            <div className="theater-osd-menu" role="menu" data-testid="library-osd-menu">
              {pipSupported ? (
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    onEnterPiP();
                    onCloseMore();
                  }}
                >
                  Picture in Picture
                </button>
              ) : null}
              {barActions.popOutOfWindow ? (
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    onOpenPopout();
                    onCloseMore();
                  }}
                >
                  {POP_OUT_OF_WINDOW_LABEL}
                </button>
              ) : null}
              <button
                type="button"
                role="menuitem"
                onClick={onToggleBlackFrame}
                data-testid="library-black-frame"
              >
                {playFrameMenuLabel(blackFrame)}
              </button>
              {plexHref ? (
                <a
                  role="menuitem"
                  href={plexHref}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={onCloseMore}
                >
                  Open in Plex
                </a>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      {ccOpen ? (
        <SubtitlePicker
          testId="library-cc-picker"
          tracks={subTracks}
          burnInTracks={burnInTracks}
          activeId={activeSub}
          onSelect={onSelectSubtitle}
          state={activeSubTrack ? subs.state : "idle"}
          error={subs.error}
          emptyMessage={subListNote}
          delaySec={subDelay}
          onDelayChange={
            activeBurnIn ? undefined : (value) => onDelayChange(clampSubtitleDelay(value))
          }
        />
      ) : null}
    </div>
  );
}

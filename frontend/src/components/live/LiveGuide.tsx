import { useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type MouseEvent } from "react";
import { formatWallTime, guideTimeScale, programCellStyle } from "../../lib/liveChannels.js";
import { liveGuideEmptyCopy } from "../../lib/liveChannelsCopy.js";
import {
  formatProgramEpisodeLabel,
  programTitle,
} from "../../lib/liveProgramDetail.js";
import LiveProgramHoverCard, { type LiveProgramHoverAnchor, type LiveProgramHoverKind } from "./LiveProgramHoverCard";

const PX_PER_HOUR = 220;

export type LiveGuideProgram = {
  title?: string;
  episode?: string | number;
  rating?: string;
  start?: number;
  isFlex?: boolean;
  [key: string]: unknown;
};

export type LiveGuideChannel = {
  id: string;
  name?: string;
  number?: number | string | null;
  kind?: string;
  poolNotice?: string;
  programs?: LiveGuideProgram[];
};

export type LiveGuideData = {
  ready?: boolean;
  reason?: string;
  channels?: LiveGuideChannel[];
  windowStart?: number;
  windowEnd?: number;
};

export type LiveGuideProps = {
  guide?: LiveGuideData | null;
  selectedChannelId?: string;
  selectedProgramKey?: string;
  onSelectChannel?: (channelId: string) => void;
  onTune?: (channelId: string, program: LiveGuideProgram | null) => void;
};

type GuideHover = {
  program: LiveGuideProgram;
  kind: LiveProgramHoverKind;
  anchor: LiveProgramHoverAnchor;
};

/**
 * Newspaper-style channel × time EPG grid.
 *
 * Layout contract (one time scale, see `guideTimeScale` in lib/liveChannels.js):
 * - The grid is snapped OUT to half-hour boundaries, so every column is exactly
 *   `PX_PER_HOUR / 2` px and the first/last tick are column edges.
 * - Time-header ticks, program cells, the now-line and the row gridlines all take
 *   their x from `scale.xForTime` (left edge = start, width = true duration).
 * - Header and rows live in ONE horizontally scrolling box (`.live-guide-scroll`),
 *   so they scroll together; the channel rail is sticky-left with row/header heights
 *   pinned to the same CSS variables as the grid rows.
 */
export default function LiveGuide({
  guide,
  selectedChannelId = "",
  selectedProgramKey = "",
  onSelectChannel,
  onTune,
}: LiveGuideProps) {
  const gridRef = useRef<HTMLDivElement | null>(null);
  const hoverLeaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [focusRow, setFocusRow] = useState(0);
  const [focusCol, setFocusCol] = useState(0);
  const [nowMs, setNowMs] = useState(Date.now());
  const [hover, setHover] = useState<GuideHover | null>(null);

  function cancelHoverLeave() {
    if (hoverLeaveTimer.current) {
      clearTimeout(hoverLeaveTimer.current);
      hoverLeaveTimer.current = null;
    }
  }

  function scheduleHoverLeave() {
    cancelHoverLeave();
    // Brief grace so the pointer can travel into the fixed hover card.
    hoverLeaveTimer.current = setTimeout(() => setHover(null), 160);
  }

  useEffect(() => () => cancelHoverLeave(), []);

  const channels = guide?.channels || [];
  const windowStart = guide?.windowStart ?? Date.now() / 1000;
  const windowEnd = guide?.windowEnd ?? windowStart + 6 * 3600;
  const scale = useMemo(
    () => guideTimeScale(windowStart, windowEnd, PX_PER_HOUR),
    [windowStart, windowEnd],
  );
  const gridWidth = scale.width;

  useEffect(() => {
    const timer = setInterval(() => setNowMs(Date.now()), 30000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!channels.length) return;
    const idx = channels.findIndex((c) => c.id === selectedChannelId);
    if (idx >= 0) setFocusRow(idx);
  }, [selectedChannelId, channels]);

  const nowLineLeft = scale.xForTime(nowMs / 1000);

  function tuneAt(row: number, col: number) {
    const channel = channels[row];
    if (!channel) return;
    const program = channel.programs?.[col];
    onSelectChannel?.(channel.id);
    onTune?.(channel.id, program || null);
  }

  function tuneStation(row: number) {
    const channel = channels[row];
    if (!channel) return;
    setFocusRow(row);
    onSelectChannel?.(channel.id);
    onTune?.(channel.id, null);
  }

  function placeHover(program: LiveGuideProgram | undefined, event: MouseEvent<HTMLElement>, kind: LiveProgramHoverKind = "guide") {
    cancelHoverLeave();
    if (!program || program.isFlex) {
      setHover(null);
      return;
    }
    const rect = event.currentTarget?.getBoundingClientRect?.();
    if (!rect) return;
    setHover({
      program,
      kind,
      anchor: { top: rect.top, bottom: rect.bottom, left: rect.left },
    });
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (!channels.length) return;
    const key = event.key;
    if (key === "ArrowUp") {
      event.preventDefault();
      setFocusRow((row) => Math.max(0, row - 1));
    } else if (key === "ArrowDown") {
      event.preventDefault();
      setFocusRow((row) => Math.min(channels.length - 1, row + 1));
    } else if (key === "ArrowLeft") {
      event.preventDefault();
      setFocusCol((col) => Math.max(0, col - 1));
    } else if (key === "ArrowRight") {
      event.preventDefault();
      const maxCol = Math.max(0, (channels[focusRow]?.programs?.length || 1) - 1);
      setFocusCol((col) => Math.min(maxCol, col + 1));
    } else if (key === "Enter") {
      event.preventDefault();
      tuneAt(focusRow, focusCol);
    }
  }

  if (!guide?.ready) {
    const empty = liveGuideEmptyCopy(guide?.reason);
    return (
      <div className="live-guide-empty" data-testid="live-guide-empty">
        <h2>{empty.title}</h2>
        <p>{empty.body}</p>
      </div>
    );
  }

  const rowsStyle = {
    width: gridWidth,
    "--guide-slot-px": `${scale.pxPerSlot}px`,
    "--guide-hour-px": `${scale.pxPerHour}px`,
  } as CSSProperties;

  return (
    <div
      className="live-guide"
      data-testid="live-guide"
      tabIndex={0}
      ref={gridRef}
      onKeyDown={onKeyDown}
    >
      <div className="live-guide-scroll">
        <div className="live-guide-rail" aria-hidden="true">
          <div className="live-guide-rail-corner">
            <span className="live-brand-mark">Projectionist</span>
            <span className="live-guide-rail-label">Live</span>
          </div>
          {channels.map((channel, row) => (
            <button
              key={channel.id}
              type="button"
              className={`live-guide-station${channel.kind === "weather" ? " live-guide-station--weather" : ""}${channel.id === selectedChannelId || row === focusRow ? " is-active" : ""}`}
              onClick={() => tuneStation(row)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") event.stopPropagation();
              }}
              aria-label={`Tune ${channel.number != null ? `${channel.number} ` : ""}${channel.name}${channel.poolNotice ? `. ${channel.poolNotice}` : ""}`}
              title={channel.poolNotice || undefined}
              data-testid="live-guide-station"
            >
              <span className="live-guide-station-num">{channel.number ?? "—"}</span>
              <span className="live-guide-station-name">{channel.name}</span>
              {channel.poolNotice ? (
                <span className="live-guide-station-notice" data-testid="live-guide-pool-notice">
                  {channel.poolNotice}
                </span>
              ) : null}
            </button>
          ))}
        </div>

        <div className="live-guide-grid-wrap" style={{ width: gridWidth }}>
          <div className="live-guide-timeline" style={{ width: gridWidth }}>
            {scale.marks.map((mark: number) => (
              <span
                key={mark}
                className="live-guide-tick"
                style={{ left: `${scale.xForTime(mark)}px`, width: `${scale.pxPerSlot}px` }}
              >
                {formatWallTime(mark)}
              </span>
            ))}
          </div>

          <div
            className="live-guide-rows"
            style={rowsStyle}
            data-testid="live-guide-rows"
          >
            {nowLineLeft >= 0 && nowLineLeft <= gridWidth ? (
              <div
                className="live-guide-now-line"
                style={{ left: `${nowLineLeft}px` }}
                data-testid="live-guide-now-line"
              />
            ) : null}
            {channels.map((channel, row) => (
              <div
                key={channel.id}
                className={`live-guide-row${row === focusRow ? " is-focused" : ""}`}
                data-testid="live-guide-row"
              >
                {(channel.programs || []).map((program, col) => {
                  const style = programCellStyle(program, scale.gridStart, scale.gridEnd, PX_PER_HOUR);
                  const title = programTitle(program) || program.title;
                  const episodeLabel =
                    formatProgramEpisodeLabel(program) || program.episode || "";
                  const key = `${channel.id}:${program.start}:${title}`;
                  const focused = row === focusRow && col === focusCol;
                  return (
                    <button
                      key={key}
                      type="button"
                      className={`live-guide-cell${focused ? " is-focused" : ""}${
                        key === selectedProgramKey ? " is-selected" : ""
                      }${program.isFlex ? " is-flex" : ""}`}
                      style={style}
                      onClick={() => {
                        setFocusRow(row);
                        setFocusCol(col);
                        setHover(null);
                        tuneAt(row, col);
                      }}
                      onMouseEnter={(event) => placeHover(program, event)}
                      onMouseLeave={scheduleHoverLeave}
                      onFocus={(event) => {
                        setFocusRow(row);
                        setFocusCol(col);
                        placeHover(program, (event as any));
                      }}
                      onBlur={scheduleHoverLeave}
                      data-testid="live-guide-cell"
                      title={episodeLabel ? `${title} — ${episodeLabel}` : title}
                    >
                      <span className="live-guide-cell-title">{title}</span>
                      {episodeLabel ? (
                        <span className="live-guide-cell-ep">{episodeLabel}</span>
                      ) : null}
                      {program.rating ? (
                        <span className="live-guide-cell-rating">{program.rating}</span>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </div>

      <LiveProgramHoverCard
        program={hover?.program}
        kind={hover?.kind || "guide"}
        open={Boolean(hover)}
        anchor={hover?.anchor}
        onKeepAlive={cancelHoverLeave}
        onClose={() => setHover(null)}
      />
    </div>
  );
}

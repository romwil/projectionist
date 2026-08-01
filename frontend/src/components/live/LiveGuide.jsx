import { useEffect, useMemo, useRef, useState } from "react";
import { formatWallTime, programCellStyle } from "../../lib/liveChannels.js";
import { liveGuideEmptyCopy } from "../../lib/liveChannelsCopy.js";
import {
  formatProgramEpisodeLabel,
  programTitle,
} from "../../lib/liveProgramDetail.js";
import LiveProgramHoverCard from "./LiveProgramHoverCard.jsx";

const PX_PER_HOUR = 220;

/**
 * Newspaper-style channel × time EPG grid.
 */
export default function LiveGuide({
  guide,
  selectedChannelId = "",
  selectedProgramKey = "",
  onSelectChannel,
  onTune,
}) {
  const gridRef = useRef(null);
  const hoverLeaveTimer = useRef(null);
  const [focusRow, setFocusRow] = useState(0);
  const [focusCol, setFocusCol] = useState(0);
  const [nowMs, setNowMs] = useState(Date.now());
  const [hover, setHover] = useState(null);

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
  const hours = Math.max(1, (windowEnd - windowStart) / 3600);
  const gridWidth = hours * PX_PER_HOUR;

  const timeMarks = useMemo(() => {
    const marks = [];
    const startAligned = Math.floor(windowStart / 1800) * 1800;
    for (let t = startAligned; t <= windowEnd; t += 1800) {
      if (t < windowStart - 60) continue;
      marks.push(t);
    }
    return marks;
  }, [windowStart, windowEnd]);

  useEffect(() => {
    const timer = setInterval(() => setNowMs(Date.now()), 30000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!channels.length) return;
    const idx = channels.findIndex((c) => c.id === selectedChannelId);
    if (idx >= 0) setFocusRow(idx);
  }, [selectedChannelId, channels]);

  const nowLineLeft = ((nowMs / 1000 - windowStart) / 3600) * PX_PER_HOUR;

  function tuneAt(row, col) {
    const channel = channels[row];
    if (!channel) return;
    const program = channel.programs?.[col];
    onSelectChannel?.(channel.id);
    onTune?.(channel.id, program);
  }

  function placeHover(program, event, kind = "guide") {
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
      x: rect.left,
      y: rect.bottom + 6,
    });
  }

  function onKeyDown(event) {
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
              className={`live-guide-station${channel.id === selectedChannelId || row === focusRow ? " is-active" : ""}`}
              onClick={() => {
                setFocusRow(row);
                onSelectChannel?.(channel.id);
              }}
              data-testid="live-guide-station"
            >
              <span className="live-guide-station-num">{channel.number ?? "—"}</span>
              <span className="live-guide-station-name">{channel.name}</span>
            </button>
          ))}
        </div>

        <div className="live-guide-grid-wrap">
          <div className="live-guide-timeline" style={{ width: gridWidth }}>
            {timeMarks.map((mark) => (
              <span
                key={mark}
                className="live-guide-tick"
                style={{ left: `${((mark - windowStart) / 3600) * PX_PER_HOUR}px` }}
              >
                {formatWallTime(mark)}
              </span>
            ))}
          </div>

          <div className="live-guide-rows" style={{ width: gridWidth }}>
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
                  const style = programCellStyle(program, windowStart, windowEnd, PX_PER_HOUR);
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
                        placeHover(program, event);
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
        x={hover?.x || 0}
        y={hover?.y || 0}
        onKeepAlive={cancelHoverLeave}
        onClose={() => setHover(null)}
      />
    </div>
  );
}

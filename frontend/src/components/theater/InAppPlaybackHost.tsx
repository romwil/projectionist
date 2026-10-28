import { useEffect, useRef, useState, type PointerEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  clearShrunkPlay,
  initialPipState,
  isLibraryPopoutPath,
  normalizeReturnTo,
  persistShrunkPlay,
  playbackMountKey,
  resolvePlaybackHost,
  watchRatingKeyFromPath,
} from "../../lib/inAppPip.js";
import { libraryWatchPath } from "../../lib/theaterPlayer.js";
import LibraryPlayer from "./LibraryPlayer";

type PipState = {
  ratingKey: string;
  returnTo: string;
  offsetMs: number;
  title: string;
  restored?: boolean;
};

type ShrinkPayload = {
  ratingKey?: string;
  offsetMs?: number;
  title?: string;
};

type PlayheadSample = {
  offsetMs?: number;
  title?: string;
  flush?: boolean;
};

function routeFromState(state: unknown): string {
  if (state && typeof state === "object" && "from" in state) {
    const from = (state as { from: unknown }).from;
    if (typeof from === "string") return from;
  }
  return "";
}

/**
 * Library Play lives here, beside the route table, so shrinking does not
 * unmount the video when chat, Explore, or search replace `/watch`.
 */
export default function InAppPlaybackHost() {
  const location = useLocation();
  const navigate = useNavigate();
  const [pip, setPip] = useState<PipState | null>(() => initialPipState(globalThis.location?.pathname || ""));
  const [dragPos, setDragPos] = useState<{ x: number; y: number } | null>(null);
  const [leaving, setLeaving] = useState(false);
  const dragRef = useRef<{ dx: number; dy: number } | null>(null);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const pipRef = useRef(pip);
  const playheadAtRef = useRef(0);
  useEffect(() => {
    pipRef.current = pip;
  }, [pip]);

  const [navTrail, setNavTrail] = useState<any>({ current: "", previous: "" });
  const here = `${location.pathname}${location.search || ""}`;
  if (navTrail.current !== here) {
    setNavTrail({ current: here, previous: navTrail.current });
  }
  const routeKey = watchRatingKeyFromPath(location.pathname);
  const popoutWindow = isLibraryPopoutPath(location.pathname);
  if (pip && routeKey && !leaving) {
    clearShrunkPlay();
    setPip(null);
  } else if (leaving && !routeKey && !popoutWindow) {
    setLeaving(false);
  }

  const session = pip && !(routeKey && !leaving) ? { presentation: "pip", ratingKey: pip.ratingKey } : null;
  const decision = resolvePlaybackHost({ pathname: location.pathname, session });
  const mountKey = playbackMountKey(decision);

  useEffect(() => {
    if (!leaving || !pip?.returnTo) return;
    if (watchRatingKeyFromPath(location.pathname)) navigate(pip.returnTo);
  }, [leaving, pip, location.pathname, navigate]);

  function shrink(next?: ShrinkPayload | null) {
    const currentKey = watchRatingKeyFromPath(location.pathname);
    const ratingKey = String(next?.ratingKey || currentKey || "").trim();
    if (!ratingKey) return;
    const explicit = routeFromState(location.state);
    const remembered = explicit || navTrail.previous;
    setDragPos(null);
    setLeaving(true);
    const nextPip: PipState = {
      ratingKey,
      returnTo: normalizeReturnTo(remembered),
      offsetMs: Math.max(0, Math.floor(Number(next?.offsetMs) || 0)),
      title: String(next?.title || ""),
    };
    persistShrunkPlay(nextPip);
    setPip(nextPip);
  }

  function rememberPlayhead(sample?: PlayheadSample | null) {
    const current = pipRef.current;
    if (!current?.ratingKey) return;
    const offsetMs = Math.max(0, Math.floor(Number(sample?.offsetMs) || 0));
    const title = String(sample?.title || current.title || "");
    const now = Date.now();
    if (!sample?.flush && now - playheadAtRef.current < 2000) return;
    playheadAtRef.current = now;
    persistShrunkPlay({ ratingKey: current.ratingKey, offsetMs, title });
  }

  function expand() {
    if (!pip?.ratingKey) return;
    setLeaving(false);
    navigate(libraryWatchPath(pip.ratingKey), {
      state: { from: `${location.pathname}${location.search || ""}` },
    });
  }

  function closePip() {
    clearShrunkPlay();
    setLeaving(false);
    setPip(null);
    setDragPos(null);
  }

  function afterPopout() {
    clearShrunkPlay();
    setLeaving(false);
    setPip(null);
    setDragPos(null);
    if (!watchRatingKeyFromPath(location.pathname)) return;
    const from = routeFromState(location.state);
    navigate(normalizeReturnTo(from || "/chat"));
  }

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    if (decision.presentation !== "pip") return;
    const target = event.target as HTMLElement | null;
    if (target?.closest?.("button, a, input, label")) return;
    if (!target?.closest?.("[data-inapp-pip-drag]")) return;
    const rect = hostRef.current?.getBoundingClientRect();
    if (!rect) return;
    dragRef.current = { dx: event.clientX - rect.left, dy: event.clientY - rect.top };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    if (!dragRef.current || !hostRef.current) return;
    const width = hostRef.current.offsetWidth;
    const height = hostRef.current.offsetHeight;
    const maxX = Math.max(0, window.innerWidth - width);
    const maxY = Math.max(0, window.innerHeight - height);
    const x = Math.min(maxX, Math.max(0, event.clientX - dragRef.current.dx));
    const y = Math.min(maxY, Math.max(0, event.clientY - dragRef.current.dy));
    setDragPos({ x, y });
  }

  function onPointerUp() {
    dragRef.current = null;
  }

  if (popoutWindow || !decision.active || !mountKey) return null;

  const floated = decision.presentation === "pip";
  const dragged = Boolean(dragPos);

  return (
    <div
      ref={hostRef}
      className="inapp-playback-host"
      data-presentation={decision.presentation}
      data-theater-mode={floated ? undefined : "true"}
      data-testid={floated ? "inapp-pip" : "inapp-playback-stage"}
      data-dragged={dragged ? "true" : "false"}
      style={dragPos ? { left: dragPos.x, top: dragPos.y } : undefined}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      {floated ? (
        <div className="inapp-pip-toolbar" data-inapp-pip-drag="true" data-testid="inapp-pip-toolbar">
          <span className="inapp-pip-toolbar-label">Playing</span>
          <button type="button" data-testid="inapp-pip-return" onClick={expand}>
            Return to player
          </button>
          <button type="button" data-testid="inapp-pip-close" onClick={closePip}>
            Close
          </button>
        </div>
      ) : null}
      <LibraryPlayer
        key={mountKey}
        ratingKey={decision.ratingKey}
        floated={floated}
        continueAtMs={pip?.restored ? pip.offsetMs ?? 0 : null}
        onPlayhead={floated ? rememberPlayhead : null as any}
        onShrink={shrink}
        onAfterPopout={afterPopout}
      />
    </div>
  );
}

import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  isLibraryPopoutPath,
  normalizeReturnTo,
  playbackMountKey,
  resolvePlaybackHost,
  watchRatingKeyFromPath,
} from "../../lib/inAppPip.js";
import { libraryWatchPath } from "../../lib/theaterPlayer.js";
import LibraryPlayer from "./LibraryPlayer.jsx";

/**
 * Library Play lives here, beside the route table, so shrinking does not
 * unmount the video when chat, Explore, or search replace `/watch`.
 */
export default function InAppPlaybackHost() {
  const location = useLocation();
  const navigate = useNavigate();
  const [pip, setPip] = useState(null);
  const [dragPos, setDragPos] = useState(null);
  const [leaving, setLeaving] = useState(false);
  const dragRef = useRef(null);
  const hostRef = useRef(null);

  const [navTrail, setNavTrail] = useState({ current: "", previous: "" });
  const here = `${location.pathname}${location.search || ""}`;
  if (navTrail.current !== here) {
    setNavTrail({ current: here, previous: navTrail.current });
  }
  const routeKey = watchRatingKeyFromPath(location.pathname);
  const popoutWindow = isLibraryPopoutPath(location.pathname);
  if (pip && routeKey && !leaving) {
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

  function shrink(next) {
    const currentKey = watchRatingKeyFromPath(location.pathname);
    const ratingKey = String(next?.ratingKey || currentKey || "").trim();
    if (!ratingKey) return;
    const explicit = typeof location.state?.from === "string" ? location.state.from : "";
    const remembered = explicit || navTrail.previous;
    setDragPos(null);
    setLeaving(true);
    setPip({
      ratingKey,
      returnTo: normalizeReturnTo(remembered),
    });
  }

  function expand() {
    if (!pip?.ratingKey) return;
    setLeaving(false);
    navigate(libraryWatchPath(pip.ratingKey), {
      state: { from: `${location.pathname}${location.search || ""}` },
    });
  }

  function closePip() {
    setLeaving(false);
    setPip(null);
    setDragPos(null);
  }

  function afterPopout() {
    setLeaving(false);
    setPip(null);
    setDragPos(null);
    if (!watchRatingKeyFromPath(location.pathname)) return;
    const from = location.state?.from;
    navigate(normalizeReturnTo(typeof from === "string" ? from : "/chat"));
  }

  function onPointerDown(event) {
    if (decision.presentation !== "pip") return;
    if (event.target.closest?.("button, a, input, label")) return;
    if (!event.target.closest?.("[data-inapp-pip-drag]")) return;
    const rect = hostRef.current?.getBoundingClientRect();
    if (!rect) return;
    dragRef.current = { dx: event.clientX - rect.left, dy: event.clientY - rect.top };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function onPointerMove(event) {
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
      style={dragged ? { left: dragPos.x, top: dragPos.y } : undefined}
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
        onShrink={shrink}
        onAfterPopout={afterPopout}
      />
    </div>
  );
}

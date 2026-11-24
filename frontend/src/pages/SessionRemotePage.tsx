import { useEffect, useRef, useState } from "react";
import { useLocation, useParams } from "react-router-dom";
import {
  decideJoinRequest,
  getAuthMe,
  listJoinRequests,
  patchSharedSession,
  postSessionCommand,
  readJoinCode,
  readSharedSession,
} from "../api/client";
import type { JsonObject } from "../api/types";
import Button from "../components/Button";
import AppShell from "../layouts/AppShell";
import {
  formatPlayhead,
  mayUseRemote,
  playheadNow,
  remoteRole,
  sessionLiveUrl,
  transportCommand,
  type RemoteRole,
  type SessionClock,
} from "../lib/sessionRemote";

type JoinAsk = { id: string; display_name: string };

function clockFrom(payload: JsonObject, previous: SessionClock | null): SessionClock {
  return {
    position_ms: Number(payload.position_ms ?? previous?.position_ms ?? 0),
    server_time_ms: Number(payload.server_time_ms ?? Date.now()),
    state: String(payload.state || previous?.state || "paused"),
  };
}

/** A second screen for a session. Commands go on the live channel. */
export default function SessionRemotePage() {
  const { sessionId = "" } = useParams();
  const location = useLocation();
  const roomName =
    String((location.state as { roomName?: string } | null)?.roomName || "").trim() || "This room";
  const [clock, setClock] = useState<SessionClock | null>(null);
  const [shown, setShown] = useState(0);
  const [role, setRole] = useState<RemoteRole>("screen");
  const [guestsMayRemote, setGuestsMayRemote] = useState(false);
  const [held, setHeld] = useState(false);
  const [code, setCode] = useState("");
  const [requests, setRequests] = useState<JoinAsk[]>([]);
  const [ended, setEnded] = useState(false);
  const [error, setError] = useState("");
  const [channel, setChannel] = useState<"connecting" | "open" | "down">("connecting");
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let closed = false;
    let opened: WebSocket | null = null;
    readSharedSession(sessionId)
      .then(async (session) => {
        if (closed) return;
        setClock(clockFrom(session, null));
        setGuestsMayRemote(Boolean(session.guests_may_remote));
        setHeld(Boolean(session.held_for_ceiling));
        const me = await getAuthMe();
        if (closed) return;
        const nextRole = remoteRole(session, String(me?.user?.id || ""));
        setRole(nextRole);
        if (nextRole !== "guest") {
          const ticket = await readJoinCode(sessionId).catch(() => null);
          if (!closed && ticket?.code) setCode(String(ticket.code));
        }
        if (nextRole === "owner") {
          const waiting = await listJoinRequests(sessionId).catch(() => null);
          if (!closed) {
            setRequests(
              (waiting?.requests || [])
                .map((row) => ({
                  id: String(row.id || ""),
                  display_name: String(row.display_name || "Someone"),
                }))
                .filter((row) => row.id),
            );
          }
        }
      })
      .catch(() => {
        if (!closed) setError("That session is not available.");
      });
    try {
      opened = new WebSocket(sessionLiveUrl(sessionId, window.location.href));
    } catch {
      opened = null;
    }
    if (opened) {
      opened.onopen = () => {
        if (!closed) setChannel("open");
      };
      opened.onerror = () => {
        if (!closed) setChannel("down");
      };
      opened.onmessage = (event) => {
        let payload: JsonObject = {};
        try {
          payload = JSON.parse(String(event.data || "{}")) as JsonObject;
        } catch {
          return;
        }
        if (payload.type === "error") {
          setError(String(payload.detail || "That command is not allowed."));
          return;
        }
        if (payload.type === "ended" || payload.state === "ended") setEnded(true);
        if ("held_for_ceiling" in payload) setHeld(Boolean(payload.held_for_ceiling));
        setClock((current) => clockFrom(payload, current));
        setError("");
      };
      socketRef.current = opened;
    }
    return () => {
      closed = true;
      opened?.close();
    };
  }, [sessionId]);

  useEffect(() => {
    const tick = () => setShown(playheadNow(clock));
    tick();
    if (clock?.state !== "playing") return undefined;
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [clock]);

  async function send(command: "play" | "pause" | "skip" | "end", seconds = 0) {
    if (command !== "end" && !mayUseRemote(role, guestsMayRemote)) return;
    if (command === "play" && held) return;
    const body = transportCommand(command, seconds);
    setError("");
    const live = socketRef.current;
    if (live && live.readyState === WebSocket.OPEN) {
      live.send(JSON.stringify(body));
      return;
    }
    try {
      const payload = (await postSessionCommand(sessionId, body)) as JsonObject;
      if (payload.type === "ended" || payload.state === "ended") setEnded(true);
      setClock((current) => clockFrom(payload, current));
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "That command is not allowed.");
    }
  }

  async function allowGuests(next: boolean) {
    setError("");
    try {
      const updated = await patchSharedSession(sessionId, { guests_may_remote: next });
      setGuestsMayRemote(Boolean(updated.guests_may_remote));
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "That change was not saved.");
    }
  }

  async function answer(requestId: string, decision: "approve" | "not_now") {
    setError("");
    try {
      await decideJoinRequest(sessionId, requestId, decision);
      setRequests((current) => current.filter((row) => row.id !== requestId));
    } catch (err) {
      setError(
        err instanceof Error && err.message ? err.message : "That request is not available.",
      );
    }
  }

  const transport = mayUseRemote(role, guestsMayRemote);

  return (
    <AppShell>
      <div className="settings-page" data-testid="session-remote">
        <h1 data-testid="session-remote-room">{roomName}</h1>
        <p data-testid="session-remote-position">{formatPlayhead(shown)}</p>
        <p data-testid="session-remote-state">{ended ? "ended" : clock?.state || "…"}</p>
        {code ? <p data-testid="session-remote-code">Code {code}</p> : null}
        {held ? (
          <p data-testid="session-remote-held">This room is paused for the rating limit.</p>
        ) : null}
        {error ? (
          <p className="field-help" role="alert" data-testid="session-remote-error">
            {error}
          </p>
        ) : null}
        {ended ? null : transport ? (
          <div className="rooms-remote">
            <Button
              variant="primary"
              data-testid="session-remote-pause"
              disabled={channel === "connecting"}
              onClick={() => void send("pause")}
            >
              Pause
            </Button>
            <Button
              variant="secondary"
              data-testid="session-remote-play"
              disabled={held}
              onClick={() => void send("play")}
            >
              Play
            </Button>
            <Button
              variant="secondary"
              data-testid="session-remote-back"
              onClick={() => void send("skip", -10)}
            >
              Back 10 seconds
            </Button>
            <Button
              variant="secondary"
              data-testid="session-remote-forward"
              onClick={() => void send("skip", 10)}
            >
              Forward 10 seconds
            </Button>
            {role === "owner" ? (
              <Button
                variant="danger"
                data-testid="session-remote-end"
                onClick={() => void send("end")}
              >
                End
              </Button>
            ) : null}
          </div>
        ) : (
          <p data-testid="session-remote-locked">
            The remote stays off until the person who started this session allows it.
          </p>
        )}
        {role === "owner" && !ended ? (
          <div data-testid="session-remote-host">
            <Button
              variant="secondary"
              data-testid="session-remote-guests"
              onClick={() => void allowGuests(!guestsMayRemote)}
            >
              {guestsMayRemote ? "Turn the guest remote off" : "Let guests use the remote"}
            </Button>
            {requests.map((row) => (
              <div key={row.id} data-testid={`join-request-${row.id}`}>
                <p>{row.display_name} wants to join.</p>
                <Button
                  variant="primary"
                  size="sm"
                  data-testid={`join-approve-${row.id}`}
                  onClick={() => void answer(row.id, "approve")}
                >
                  Approve
                </Button>
                <Button
                  size="sm"
                  data-testid={`join-decline-${row.id}`}
                  onClick={() => void answer(row.id, "not_now")}
                >
                  Not now
                </Button>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}

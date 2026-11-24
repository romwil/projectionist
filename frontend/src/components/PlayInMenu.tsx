import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getFeatures, listRooms, openSharedSession } from "../api/client";
import { capabilityOn, openSessionBody, roomRows, type RoomRow } from "../lib/sessionRemote";

/** Play in a named screen. Play itself still starts on this page. */
export default function PlayInMenu({ ratingKey }: { ratingKey: string }) {
  const navigate = useNavigate();
  const [rooms, setRooms] = useState<RoomRow[] | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getFeatures()
      .then(async (features) => {
        if (!capabilityOn(features, "rooms") || !capabilityOn(features, "session_object"))
          return [];
        const payload = await listRooms();
        return roomRows(payload);
      })
      .then((rows) => {
        if (!cancelled) setRooms(rows);
      })
      .catch(() => {
        if (!cancelled) setRooms([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!ratingKey || !rooms || rooms.length === 0) return null;

  async function start(room: RoomRow) {
    setError("");
    try {
      const session = await openSharedSession(openSessionBody(room.id, ratingKey));
      const id = String(session?.id || "");
      if (!id) throw new Error("That room is not available.");
      navigate(`/remote/${encodeURIComponent(id)}`, { state: { roomName: room.name } });
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "That room is not available.");
    }
  }

  return (
    <div className="play-in">
      <button
        type="button"
        className="title-cta title-cta-ghost title-cta-secondary"
        data-testid="play-in-button"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((value) => !value)}
      >
        Play in…
      </button>
      {open ? (
        <div className="play-in-menu" role="menu" data-testid="play-in-menu">
          {rooms.map((room) => (
            <button
              key={room.id}
              type="button"
              role="menuitem"
              className="play-in-room"
              data-testid={`play-in-${room.id}`}
              onClick={() => void start(room)}
            >
              {room.name}
            </button>
          ))}
        </div>
      ) : null}
      {error ? (
        <p className="field-help" role="alert" data-testid="play-in-error">
          {error}
        </p>
      ) : null}
    </div>
  );
}

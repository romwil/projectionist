import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getFeatures, joinRoom, listRooms, renameRoom } from "../../api/client";
import type { JsonObject } from "../../api/types";
import Button from "../../components/Button";
import SettingsPageHeader from "../../components/settings/SettingsPageHeader";
import SettingsPanel from "../../components/settings/SettingsPanel";
import { capabilityOn, joinSentence, roomRows, type RoomRow } from "../../lib/sessionRemote";

/** Named screens. The list does not say what is playing. */
export default function RoomsPage() {
  const navigate = useNavigate();
  const [rooms, setRooms] = useState<RoomRow[] | null>(null);
  const [available, setAvailable] = useState(true);
  const [names, setNames] = useState<Record<string, string>>({});
  const [codes, setCodes] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  function apply(rows: RoomRow[]) {
    setRooms(rows);
    setNames(Object.fromEntries(rows.map((room) => [room.id, room.name])));
  }

  useEffect(() => {
    let cancelled = false;
    getFeatures()
      .then(async (features) => {
        if (!capabilityOn(features, "rooms")) return null;
        return roomRows(await listRooms());
      })
      .then((rows) => {
        if (cancelled) return;
        if (rows === null) {
          setAvailable(false);
          setRooms([]);
          return;
        }
        apply(rows);
      })
      .catch(() => {
        if (!cancelled) {
          setRooms([]);
          setError("Could not load rooms.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function save(room: RoomRow) {
    setError("");
    setNotice("");
    const name = String(names[room.id] || "").trim();
    try {
      const updated = (await renameRoom(room.id, name)) as JsonObject;
      const nextName = String(updated?.name || name);
      setRooms((current) =>
        (current || []).map((item) => (item.id === room.id ? { ...item, name: nextName } : item)),
      );
      setNotice(`${nextName} is saved.`);
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "That name was not saved.");
    }
  }

  async function ask(room: RoomRow) {
    setError("");
    setNotice("");
    try {
      const result = (await joinRoom(room.id, codes[room.id] || "")) as JsonObject;
      const status = String(result?.status || "");
      if (status === "joined" && result.id) {
        navigate(`/remote/${encodeURIComponent(String(result.id))}`, {
          state: { roomName: room.name },
        });
        return;
      }
      const sentence = joinSentence(status);
      setNotice(sentence || "That room is not open.");
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "That room is not open.");
    }
  }

  return (
    <div className="settings-page" data-testid="rooms-page">
      <SettingsPageHeader title="Rooms" testId="rooms-heading">
        These are the screens in the household. The list is only the name.
      </SettingsPageHeader>
      <SettingsPanel testId="rooms-list">
        {rooms === null ? <p className="field-help">Loading…</p> : null}
        {!available ? (
          <p className="field-help" data-testid="rooms-unavailable">
            Rooms are not available on this server.
          </p>
        ) : null}
        {error ? (
          <p className="field-help" role="alert" data-testid="rooms-error">
            {error}
          </p>
        ) : null}
        {notice ? (
          <p className="field-help" data-testid="rooms-notice">
            {notice}
          </p>
        ) : null}
        {available && rooms && rooms.length === 0 ? (
          <p className="field-help" data-testid="rooms-empty">
            No screens are in this household yet.
          </p>
        ) : null}
        {rooms?.map((room) => (
          <div key={room.id} className="rooms-row" data-testid={`room-${room.id}`}>
            <p data-testid={`room-name-${room.id}`}>{room.name}</p>
            <label htmlFor={`room-rename-${room.id}`}>
              Name
              <input
                id={`room-rename-${room.id}`}
                value={names[room.id] ?? room.name}
                aria-label={`Name for ${room.name}`}
                data-testid={`room-rename-${room.id}`}
                onChange={(event) =>
                  setNames((current) => ({ ...current, [room.id]: event.target.value }))
                }
              />
            </label>
            <Button
              variant="secondary"
              size="sm"
              data-testid={`room-save-${room.id}`}
              onClick={() => void save(room)}
            >
              Save
            </Button>
            <label htmlFor={`room-code-${room.id}`}>
              Code
              <input
                id={`room-code-${room.id}`}
                value={codes[room.id] ?? ""}
                aria-label={`Code for ${room.name}`}
                data-testid={`room-code-${room.id}`}
                autoComplete="off"
                onChange={(event) =>
                  setCodes((current) => ({ ...current, [room.id]: event.target.value }))
                }
              />
            </label>
            <Button
              variant="primary"
              size="sm"
              data-testid={`room-join-${room.id}`}
              onClick={() => void ask(room)}
            >
              Join
            </Button>
          </div>
        ))}
      </SettingsPanel>
    </div>
  );
}

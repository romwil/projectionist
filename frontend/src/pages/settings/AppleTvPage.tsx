import { useEffect, useState, type FormEvent } from "react";
import { claimAppleTv, listPairedDevices, revokeAppleTv, throwToAppleTv } from "../../api/client";
import type { JsonObject } from "../../api/types";
import Button from "../../components/Button";
import SettingsPageHeader from "../../components/settings/SettingsPageHeader";
import SettingsPanel from "../../components/settings/SettingsPanel";

function errorText(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

type PairedTv = {
  id: string;
  label: string;
  kind: string;
  display_name: string;
  can_revoke: boolean;
  is_youth: boolean;
};

function asTv(row: JsonObject): PairedTv {
  return {
    id: String(row.id || ""),
    label: String(row.label || "Apple TV"),
    kind: String(row.kind || "tv"),
    display_name: String(row.display_name || ""),
    can_revoke: Boolean(row.can_revoke),
    is_youth: Boolean(row.is_youth),
  };
}

/** Claim a code from the Apple TV, then send one title or station to it. */
export default function AppleTvPage() {
  const [code, setCode] = useState("");
  const [claiming, setClaiming] = useState(false);
  const [claimError, setClaimError] = useState("");
  const [claimStatus, setClaimStatus] = useState("");
  const [devices, setDevices] = useState<PairedTv[] | null>(null);
  const [listError, setListError] = useState("");
  const [kind, setKind] = useState<"title" | "station">("title");
  const [mediaType, setMediaType] = useState<"movie" | "show">("movie");
  const [itemId, setItemId] = useState("");
  const [stationId, setStationId] = useState("");
  const [busyId, setBusyId] = useState("");
  const [actionError, setActionError] = useState("");
  const [actionStatus, setActionStatus] = useState("");

  function loadDevices() {
    return listPairedDevices()
      .then((data) => {
        setListError("");
        setDevices((data?.devices || []).map(asTv));
      })
      .catch((error: unknown) => {
        setDevices([]);
        setListError(errorText(error, "Could not load paired TVs."));
      });
  }

  useEffect(() => {
    void loadDevices();
  }, []);

  async function claim(event: FormEvent) {
    event.preventDefault();
    const trimmed = code.trim();
    if (!trimmed) return;
    setClaiming(true);
    setClaimError("");
    setClaimStatus("");
    try {
      await claimAppleTv(trimmed);
      setCode("");
      setClaimStatus("That Apple TV is signed in as you.");
      await loadDevices();
    } catch (error: unknown) {
      setClaimError(errorText(error, "That code did not work."));
    } finally {
      setClaiming(false);
    }
  }

  async function send(deviceId: string) {
    setBusyId(deviceId);
    setActionError("");
    setActionStatus("");
    const payload =
      kind === "station"
        ? { kind: "station", station_id: stationId.trim() }
        : {
            kind: "title",
            media_type: mediaType,
            item_id: itemId.trim(),
            id_type: "rating_key",
          };
    try {
      await throwToAppleTv(deviceId, payload);
      setActionStatus("Sent. The TV opens it the next time it checks in.");
    } catch (error: unknown) {
      setActionError(errorText(error, "Could not send that to the TV."));
    } finally {
      setBusyId("");
    }
  }

  async function remove(deviceId: string, message?: string) {
    setBusyId(deviceId);
    setActionError("");
    setActionStatus("");
    try {
      await revokeAppleTv(deviceId);
      setActionStatus(
        message || "That Apple TV was removed. It will ask for a new code.",
      );
      await loadDevices();
    } catch (error: unknown) {
      setActionError(errorText(error, "Could not remove that TV."));
    } finally {
      setBusyId("");
    }
  }

  const screens = (devices || []).filter((device) => device.kind === "tv");
  const others = (devices || []).filter((device) => device.kind !== "tv");

  return (
    <>
      <SettingsPageHeader
        title="Devices"
        testId="apple-tv-settings"
        lead="Enter the code on the TV. The person signed in here is who that TV becomes. A new browser or phone is listed below, and you can remove it."
      />

      <SettingsPanel title="Enter this code" testId="apple-tv-claim">
        <form onSubmit={claim}>
          <label className="settings-field" htmlFor="apple-tv-code">
            <span>Code on the TV</span>
            <input
              id="apple-tv-code"
              type="text"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              value={code}
              disabled={claiming}
              onChange={(event) => setCode(event.target.value)}
              data-testid="apple-tv-code"
            />
          </label>
          <Button
            variant="primary"
            type="submit"
            disabled={claiming || !code.trim()}
            data-testid="apple-tv-claim-submit"
          >
            {claiming ? "Checking…" : "Claim this TV"}
          </Button>
        </form>
        {claimError ? (
          <p className="field-help" role="alert" data-testid="apple-tv-claim-error">
            {claimError}
          </p>
        ) : null}
        {claimStatus ? (
          <p className="field-help" data-testid="apple-tv-claim-status">
            {claimStatus}
          </p>
        ) : null}
      </SettingsPanel>

      <SettingsPanel
        title="Signed-in devices"
        lead="A new browser or phone shows up here. Remove it if you don't recognize the sign-in."
        testId="signed-in-devices"
      >
        {devices && others.length === 0 ? (
          <p className="field-help" data-testid="signed-in-devices-empty">
            No other device has signed in.
          </p>
        ) : null}
        {others.map((device) => (
          <div key={device.id} data-testid={`signed-in-device-${device.id}`}>
            <p>
              {device.label}
              {device.display_name ? ` · signed in as ${device.display_name}` : ""}
            </p>
            {device.can_revoke ? (
              <Button
                variant="danger"
                disabled={busyId === device.id}
                onClick={() => void remove(device.id, "That sign-in was removed.")}
              >
                Remove
              </Button>
            ) : null}
          </div>
        ))}
      </SettingsPanel>

      <SettingsPanel
        title="Send something"
        lead="One title or one station. A removed TV will say so in plain language."
        testId="apple-tv-throw"
      >
        {listError ? (
          <p className="field-help" role="alert">
            {listError}
          </p>
        ) : null}
        {devices && screens.length === 0 ? (
          <p className="field-help" data-testid="apple-tv-empty">
            No Apple TV is paired yet.
          </p>
        ) : null}
        <label className="settings-field" htmlFor="apple-tv-kind">
          <span>What to send</span>
          <select
            id="apple-tv-kind"
            value={kind}
            onChange={(event) => setKind(event.target.value === "station" ? "station" : "title")}
          >
            <option value="title">A library title</option>
            <option value="station">A live station</option>
          </select>
        </label>
        {kind === "title" ? (
          <>
            <label className="settings-field" htmlFor="apple-tv-media-type">
              <span>Movie or show</span>
              <select
                id="apple-tv-media-type"
                value={mediaType}
                onChange={(event) => setMediaType(event.target.value === "show" ? "show" : "movie")}
              >
                <option value="movie">Movie</option>
                <option value="show">Show</option>
              </select>
            </label>
            <label className="settings-field" htmlFor="apple-tv-item">
              <span>Library rating key</span>
              <input
                id="apple-tv-item"
                type="text"
                autoComplete="off"
                spellCheck={false}
                value={itemId}
                onChange={(event) => setItemId(event.target.value)}
                data-testid="apple-tv-item"
              />
            </label>
          </>
        ) : (
          <label className="settings-field" htmlFor="apple-tv-station">
            <span>Station</span>
            <input
              id="apple-tv-station"
              type="text"
              autoComplete="off"
              spellCheck={false}
              value={stationId}
              onChange={(event) => setStationId(event.target.value)}
              data-testid="apple-tv-station"
            />
          </label>
        )}
        {screens.map((device) => (
          <div key={device.id} data-testid={`apple-tv-device-${device.id}`}>
            <p>
              {device.label}
              {device.display_name ? ` · signed in as ${device.display_name}` : ""}
              {device.is_youth ? " · youth" : ""}
            </p>
            <Button
              variant="primary"
              disabled={busyId === device.id || (kind === "title" ? !itemId.trim() : !stationId.trim())}
              onClick={() => void send(device.id)}
            >
              {busyId === device.id ? "Sending…" : "Send to this TV"}
            </Button>
            {device.can_revoke ? (
              <Button variant="danger" disabled={busyId === device.id} onClick={() => void remove(device.id)}>
                Remove this TV
              </Button>
            ) : null}
          </div>
        ))}
        {actionError ? (
          <p className="field-help" role="alert" data-testid="apple-tv-action-error">
            {actionError}
          </p>
        ) : null}
        {actionStatus ? (
          <p className="field-help" data-testid="apple-tv-action-status">
            {actionStatus}
          </p>
        ) : null}
      </SettingsPanel>
    </>
  );
}

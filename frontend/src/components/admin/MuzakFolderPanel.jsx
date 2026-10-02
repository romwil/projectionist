import { useEffect, useState } from "react";
import { browseLiveMedia, saveLiveMuzakFolder } from "../../api/client";

/**
 * Owner picker for the Weather Channel music folder.
 * Roots are container-visible media paths; bind mounts are marked Shared in.
 */
export default function MuzakFolderPanel({ currentPath = "", onSaved }) {
  const [browserPath, setBrowserPath] = useState("");
  const [entries, setEntries] = useState([]);
  const [parent, setParent] = useState(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const savedPath = currentPath || "";

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setBusy(true);
      try {
        const payload = await browseLiveMedia(browserPath);
        if (cancelled) return;
        setEntries(Array.isArray(payload?.entries) ? payload.entries : []);
        setParent(payload?.parent ?? null);
        setNote(payload?.note || "");
        setStatus("");
      } catch (error) {
        if (!cancelled) {
          setEntries([]);
          setStatus(error?.message || "Could not open that folder.");
        }
      } finally {
        if (!cancelled) setBusy(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [browserPath]);

  async function handleSave(path) {
    setBusy(true);
    setStatus("");
    try {
      const payload = await saveLiveMuzakFolder(path);
      const next = payload?.muzak_folder || "";
      onSaved?.(next);
      setStatus(
        next
          ? `Music folder set to ${next}.`
          : "Music folder cleared. Weather plays without music.",
      );
    } catch (error) {
      setStatus(error?.message || "Could not save that folder.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="service-fields muzak-folder-panel" data-testid="live-muzak-folder">
      <h3 className="muzak-folder-title">Weather Channel music</h3>
      <p className="wizard-note">
        Choose a folder of audio this container can see. Folders marked <strong>Shared in</strong>{" "}
        are mounted from the host (for example preroll, movies, or TV). The rest of the container
        stays hidden. If this is empty, the Weather Channel says so and plays the forecast without
        music.
      </p>
      <p data-testid="live-muzak-current">
        {savedPath ? (
          <>
            Current folder: <code>{savedPath}</code>
          </>
        ) : (
          "No music folder yet."
        )}
      </p>
      <div className="media-browser" data-testid="live-media-browser">
        <div className="media-browser-nav">
          {browserPath ? (
            <button
              type="button"
              className="ghost"
              data-testid="live-media-up"
              disabled={busy}
              onClick={() => setBrowserPath(parent || "")}
            >
              Up
            </button>
          ) : (
            <span className="muted">Media folders</span>
          )}
          {browserPath ? <code>{browserPath}</code> : null}
          {browserPath ? (
            <button
              type="button"
              className="ghost"
              data-testid="live-muzak-use-folder"
              disabled={busy}
              onClick={() => handleSave(browserPath)}
            >
              Use this folder
            </button>
          ) : null}
        </div>
        <ul className="media-browser-list">
          {entries.map((entry) => (
            <li key={entry.path}>
              <button
                type="button"
                className={`media-browser-row${entry.bind_mount ? " is-mount" : ""}`}
                data-testid={`live-media-entry-${entry.name}`}
                data-bind-mount={entry.bind_mount ? "true" : "false"}
                disabled={busy}
                onClick={() => setBrowserPath(entry.path)}
              >
                <span>{entry.name}</span>
                {entry.bind_mount ? <span className="media-browser-badge">Shared in</span> : null}
              </button>
            </li>
          ))}
        </ul>
        {!busy && entries.length === 0 ? <p className="muted">No folders here.</p> : null}
      </div>
      {note ? <p className="field-help">{note}</p> : null}
      {savedPath ? (
        <button
          type="button"
          className="ghost"
          data-testid="live-muzak-clear"
          disabled={busy}
          onClick={() => handleSave("")}
        >
          Clear music folder
        </button>
      ) : null}
      {status ? (
        <p className="muzak-folder-status" role="status" data-testid="live-muzak-status">
          {status}
        </p>
      ) : null}
    </div>
  );
}

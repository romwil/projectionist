import { useEffect, useState } from "react";
import {
  getAheadOfTimeCopies,
  removeAheadOfTimeCopy,
  saveAheadOfTimeCopies,
} from "../../api/client";

type CopyRow = {
  rating_key?: string;
  title?: string;
  status?: string;
  file_size?: number;
  above_1080p?: boolean;
  watch_count?: number;
};

type CopiesBody = {
  output_dir?: string;
  budget_bytes?: number;
  used_bytes?: number;
  queue?: CopyRow[];
};

const GIB = 1024 * 1024 * 1024;

function formatBytes(bytes: number): string {
  const value = Number(bytes) || 0;
  const gib = value / GIB;
  if (Math.abs(gib) >= 0.1) return `${gib.toFixed(1)} GiB`;
  return `${Math.round(value / (1024 * 1024))} MiB`;
}

/**
 * Owner controls for copies made ahead of time. This panel does not start an encode.
 */
export default function CopiesAhead() {
  const [folder, setFolder] = useState("");
  const [budget, setBudget] = useState("200");
  const [body, setBody] = useState<CopiesBody | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    getAheadOfTimeCopies()
      .then((payload) => {
        if (!live) return;
        const next = payload as CopiesBody;
        setBody(next);
        setFolder(String(next.output_dir || ""));
        const gib = Number(next.budget_bytes || 0) / GIB;
        if (gib > 0) setBudget(String(Math.round(gib)));
      })
      .catch((err: { message?: string }) => {
        if (live) setError(err?.message || "Couldn’t load the copy queue.");
      });
    return () => {
      live = false;
    };
  }, []);

  async function save() {
    setBusy(true);
    setError("");
    try {
      const next = (await saveAheadOfTimeCopies(folder.trim(), Number(budget))) as CopiesBody;
      setBody(next);
    } catch (err) {
      setError((err as { message?: string })?.message || "Couldn’t save that folder.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(ratingKey: string) {
    setError("");
    try {
      const next = (await removeAheadOfTimeCopy(ratingKey)) as CopiesBody;
      setBody(next);
    } catch (err) {
      setError((err as { message?: string })?.message || "Couldn’t remove that copy.");
    }
  }

  const queue = body?.queue || [];
  const used = Number(body?.used_bytes || 0);
  const limit = Number(body?.budget_bytes || 200 * GIB);

  return (
    <div className="playability-report" data-testid="copies-ahead">
      <h4>Copies ahead of time</h4>
      <p className="field-help">
        A folder outside every Plex library. The queue starts with titles above 1080p, then the
        most-watched, until the disk budget. One encode runs at a time, from 1:00 a.m. to 6:00 a.m.
        A partial file is not played.
      </p>
      <label className="field-help">
        Output folder
        <input
          id="copies-folder"
          data-testid="copies-folder"
          value={folder}
          onChange={(event) => setFolder(event.target.value)}
        />
      </label>
      <label className="field-help">
        Disk budget (GiB)
        <input
          id="copies-budget"
          data-testid="copies-budget"
          inputMode="decimal"
          value={budget}
          onChange={(event) => setBudget(event.target.value)}
        />
      </label>
      <button type="button" data-testid="copies-save" disabled={busy} onClick={() => void save()}>
        {busy ? "Saving…" : "Save copy folder"}
      </button>
      {error ? (
        <p className="status status-error" data-testid="copies-error">
          {error}
        </p>
      ) : null}
      <p className="field-help" data-testid="copies-used">
        Used {formatBytes(used)} of {formatBytes(limit)}.
      </p>
      {queue.length ? (
        <ul className="playability-titles" data-testid="copies-queue">
          {queue.map((row) => {
            const key = String(row.rating_key || "");
            const status = String(row.status || "queued");
            return (
              <li key={key} data-testid={`copies-row-${key}`}>
                <strong>{row.title || key}</strong>
                <span className="field-help">
                  {status}
                  {row.above_1080p ? " · above 1080p" : ""}
                  {row.watch_count ? ` · ${row.watch_count} views` : ""}
                  {row.file_size ? ` · ${formatBytes(Number(row.file_size))}` : ""}
                </span>
                {status === "ready" ? (
                  <button type="button" data-testid={`copies-remove-${key}`} onClick={() => void remove(key)}>
                    Remove copy
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="field-help" data-testid="copies-empty">
          No copies queued yet. Refresh the playability report to rank the library.
        </p>
      )}
    </div>
  );
}

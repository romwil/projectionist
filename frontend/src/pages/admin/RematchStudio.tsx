import { useState } from "react";
import { api } from "../../api/client";
import {
  INVESTIGATORS_NOTE,
  folderColumnCopy,
  identityKindLabel,
  plexColumnCopy,
  radarrColumnCopy,
} from "../../lib/rematchStudio.js";

/**
 * Owner Rematch studio — Plex GUID vs Radarr TMDB vs folder (Presence / Savages).
 */

type SettingsBag = {
  tunarr?: Record<string, unknown>;
  features?: Record<string, unknown>;
  plex_movie_section?: string;
  plex_tv_section?: string;
  llm_provider?: string;
  seerr?: Record<string, unknown>;
  [key: string]: unknown;
};

type ActionAlert = {
  area?: string;
  type?: string;
  message?: string;
  block?: string;
  details?: unknown;
} | null;

type SetActionFeedback = (
  area: string,
  type?: string,
  message?: string,
  options?: Record<string, unknown>,
) => void;

type PersistSettings = (patch: Record<string, unknown>) => Promise<unknown> | unknown;

type CertifiedBadgeComponent = React.ComponentType<{
  certified?: boolean;
  testing?: boolean;
  serviceId?: string;
}>;


/** Props for RematchStudio. */
type RematchStudioProps = {
  onInvestigate?: (item: Record<string, unknown>) => void;
  onHighlight?: (item: Record<string, unknown>) => void;
};

export default function RematchStudio({ onInvestigate, onHighlight }: RematchStudioProps) {
  const [scan, setScan] = useState<any | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [actingId, setActingId] = useState("");

  const items = Array.isArray(scan?.items) ? scan.items : [];

  async function handleScan() {
    setError("");
    setBusy(true);
    try {
      const next = await api("/admin/rematch/scan");
      setScan(next);
    } catch (err: any) {
      setError((err as { message?: string }).message || "Could not scan identities.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSkip(item: any) {
    setActingId(`skip-${item.id}`);
    setError("");
    try {
      await api("/admin/rematch/skip", {
        method: "POST",
        body: JSON.stringify({ item_id: item.id, skipped: true }),
      });
      setScan((prev: any) => {
        if (!prev) return prev;
        return { ...prev, items: (prev.items || []).filter((row: any) => row.id !== item.id) };
      });
    } catch (err: any) {
      setError((err as { message?: string }).message || "Could not skip.");
    } finally {
      setActingId("");
    }
  }

  async function handleRetry(item: any) {
    setActingId(`retry-${item.id}`);
    setError("");
    try {
      const result = await api("/admin/rematch/retry", {
        method: "POST",
        body: JSON.stringify({ item_id: item.id }),
      });
      if (result?.ok) {
        setScan((prev: any) => {
          if (!prev) return prev;
          return { ...prev, items: (prev.items || []).filter((row: any) => row.id !== item.id) };
        });
      } else if (result?.item) {
        setScan((prev: any) => {
          if (!prev) return prev;
          return {
            ...prev,
            items: (prev.items || []).map((row: any) => (row.id === item.id ? result.item : row)),
          };
        });
        setError(result.message || "Still a mismatch.");
      }
    } catch (err: any) {
      setError((err as { message?: string }).message || "Retry failed.");
    } finally {
      setActingId("");
    }
  }

  return (
    <section className="config-section" data-testid="rematch-studio-card" id="rematch-studio">
      <h2>Rematch studio</h2>
      <p className="wizard-note">{INVESTIGATORS_NOTE}</p>
      <p className="wizard-note">
        Movies only. Plex GUID vs Radarr TMDB vs folder — the Presence / Savages class of bug.
        Same title is not the same identity when the path already belongs to someone else.
      </p>
      <div className="config-actions">
        <button
          type="button"
          className="primary"
          data-testid="rematch-scan"
          onClick={handleScan}
          disabled={busy}
        >
          {busy ? "Scanning…" : "Scan identities"}
        </button>
      </div>
      {scan?.radarr_note ? (
        <p className="status status-secondary" data-testid="rematch-radarr-note">
          {scan.radarr_note}
        </p>
      ) : null}
      {scan && !items.length ? (
        <p className="status status-secondary" data-testid="rematch-empty">
          No identity mismatches right now.
        </p>
      ) : null}
      {items.length ? (
        <p className="status status-secondary" data-testid="rematch-counts">
          {items.length} to rematch
          {scan?.counts?.path_conflict ? ` · ${scan.counts.path_conflict} path conflicts` : ""}
          {scan?.counts?.title_collision ? ` · ${scan.counts.title_collision} same-title` : ""}
          {scan?.counts?.needs_plex_id ? ` · ${scan.counts.needs_plex_id} need a Plex id` : ""}
        </p>
      ) : null}
      {items.map((row: any) => (
        <div
          key={row.id}
          className="config-advanced-details"
          data-testid={`rematch-row-${row.id}`}
          data-kind={row.kind}
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr 1fr",
            gap: 16,
            marginTop: 16,
            paddingTop: 16,
            borderTop: "1px solid var(--border-subtle)",
          }}
        >
          <div data-testid={`rematch-plex-${row.id}`}>
            <p>
              <strong>Plex GUID</strong>
            </p>
            <p className="status status-secondary">{plexColumnCopy(row)}</p>
          </div>
          <div data-testid={`rematch-radarr-${row.id}`}>
            <p>
              <strong>Radarr TMDB</strong>
            </p>
            <p className="status status-secondary">{radarrColumnCopy(row)}</p>
          </div>
          <div data-testid={`rematch-folder-${row.id}`}>
            <p>
              <strong>Folder</strong>
            </p>
            <p className="status status-secondary">{folderColumnCopy(row)}</p>
          </div>
          <div style={{ gridColumn: "1 / -1" }}>
            <p className="wizard-note" data-testid={`rematch-kind-${row.id}`}>
              {identityKindLabel(row.kind, row.same_title)}
            </p>
            <p className="status status-secondary">{row.message}</p>
            <div className="config-actions">
              {(row.actions || []).includes("rematch") ? (
                <button
                  type="button"
                  className="ghost"
                  data-testid={`rematch-open-${row.id}`}
                  onClick={() => onHighlight?.(row)}
                >
                  Rematch
                </button>
              ) : null}
              {(row.actions || []).includes("retry") ? (
                <button
                  type="button"
                  className="ghost"
                  data-testid={`rematch-retry-${row.id}`}
                  onClick={() => handleRetry(row)}
                  disabled={actingId === `retry-${row.id}`}
                >
                  {actingId === `retry-${row.id}` ? "Retrying…" : "Retry"}
                </button>
              ) : null}
              {(row.actions || []).includes("skip") ? (
                <button
                  type="button"
                  className="ghost"
                  data-testid={`rematch-skip-${row.id}`}
                  onClick={() => handleSkip(row)}
                  disabled={actingId === `skip-${row.id}`}
                >
                  Skip
                </button>
              ) : null}
              {(row.actions || []).includes("investigate") ? (
                <button
                  type="button"
                  className="ghost"
                  data-testid={`rematch-investigate-${row.id}`}
                  onClick={() => onInvestigate?.(row)}
                >
                  Investigate
                </button>
              ) : null}
            </div>
          </div>
        </div>
      ))}
      {error ? (
        <p className="status status-error" data-testid="rematch-error">
          {error}
        </p>
      ) : null}
    </section>
  );
}

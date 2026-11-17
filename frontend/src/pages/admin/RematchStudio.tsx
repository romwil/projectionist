import { useState } from "react";
import { useConfirmModal } from "../../hooks/useConfirmModal";
import { api } from "../../api/client";
import {
  INVESTIGATORS_NOTE,
  USE_PLEX_CONFIRM,
  USE_RADARR_CONFIRM,
  folderColumnCopy,
  identityKindLabel,
  plexColumnCopy,
  primaryRepairAction,
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
  const { confirm, modal } = useConfirmModal();

  const items = Array.isArray(scan?.items) ? scan.items : [];
  const pathConflictIds = items
    .filter((row: any) => String(row?.kind || "") === "path_conflict")
    .map((row: any) => Number(row.id))
    .filter((id: number) => Number.isFinite(id) && id > 0);

  function removeOrReplace(itemId: number, nextItem?: any) {
    setScan((prev: any) => {
      if (!prev) return prev;
      if (nextItem) {
        return {
          ...prev,
          items: (prev.items || []).map((row: any) => (row.id === itemId ? nextItem : row)),
        };
      }
      return { ...prev, items: (prev.items || []).filter((row: any) => row.id !== itemId) };
    });
  }

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
      removeOrReplace(item.id);
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
        removeOrReplace(item.id);
      } else if (result?.item) {
        removeOrReplace(item.id, result.item);
        setError(result.message || "Still a mismatch.");
      }
    } catch (err: any) {
      setError((err as { message?: string }).message || "Retry failed.");
    } finally {
      setActingId("");
    }
  }

  async function handleAdopt(item: any, side: "radarr" | "plex") {
    const body = side === "radarr" ? USE_RADARR_CONFIRM : USE_PLEX_CONFIRM;
    const title = side === "radarr" ? "Use Radarr’s identity" : "Use Plex’s identity";
    if (!(await confirm({ title, body, confirmLabel: title }))) return;
    setActingId(`use-${side}-${item.id}`);
    setError("");
    try {
      const result = await api(`/admin/rematch/adopt-${side}`, {
        method: "POST",
        body: JSON.stringify({ item_id: item.id, confirm: true }),
      });
      if (result?.ok) {
        removeOrReplace(item.id);
      } else {
        setError(result?.message || "Could not adopt identity.");
      }
    } catch (err: any) {
      setError((err as { message?: string }).message || "Could not adopt identity.");
    } finally {
      setActingId("");
    }
  }

  async function handleRecheckAll() {
    setBusy(true);
    setError("");
    try {
      const result = await api("/admin/rematch/recheck", {
        method: "POST",
        body: JSON.stringify({ item_ids: pathConflictIds.length ? pathConflictIds : null }),
      });
      const cleared = new Set(
        (Array.isArray(result?.results) ? result.results : [])
          .filter((row: any) => row?.ok)
          .map((row: any) => Number(row?.item?.id ?? row?.id)),
      );
      setScan((prev: any) => {
        if (!prev) return prev;
        return {
          ...prev,
          items: (prev.items || []).filter((row: any) => !cleared.has(Number(row.id))),
        };
      });
      if (!cleared.size) {
        setError(result?.api_note || "No path conflicts cleared — identities still differ.");
      }
    } catch (err: any) {
      setError((err as { message?: string }).message || "Re-check failed.");
    } finally {
      setBusy(false);
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
      {scan?.api_note ? (
        <p className="wizard-note" data-testid="rematch-api-note">
          {scan.api_note}
        </p>
      ) : null}
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
        {pathConflictIds.length ? (
          <button
            type="button"
            className="ghost"
            data-testid="rematch-recheck-all"
            onClick={handleRecheckAll}
            disabled={busy}
          >
            Re-check path conflicts
          </button>
        ) : null}
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
              {(row.actions || []).includes("use_radarr") ? (
                <button
                  type="button"
                  className={primaryRepairAction(row.actions) === "use_radarr" ? "primary" : "ghost"}
                  data-testid={`rematch-use-radarr-${row.id}`}
                  onClick={() => handleAdopt(row, "radarr")}
                  disabled={actingId === `use-radarr-${row.id}`}
                >
                  Use Radarr’s identity
                </button>
              ) : null}
              {(row.actions || []).includes("use_plex") ? (
                <button
                  type="button"
                  className="ghost"
                  data-testid={`rematch-use-plex-${row.id}`}
                  onClick={() => handleAdopt(row, "plex")}
                  disabled={actingId === `use-plex-${row.id}`}
                >
                  Use Plex’s identity
                </button>
              ) : null}
              {(row.actions || []).includes("retry") ? (
                <button
                  type="button"
                  className={primaryRepairAction(row.actions) === "retry" ? "primary" : "ghost"}
                  data-testid={`rematch-retry-${row.id}`}
                  onClick={() => handleRetry(row)}
                  disabled={actingId === `retry-${row.id}`}
                >
                  {actingId === `retry-${row.id}` ? "Retrying…" : "Retry"}
                </button>
              ) : null}
              {(row.actions || []).includes("rematch") ? (
                <button
                  type="button"
                  className="ghost"
                  data-testid={`rematch-open-${row.id}`}
                  onClick={() => onHighlight?.(row)}
                >
                  Open Rematch studio
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
      {modal}
    </section>
  );
}

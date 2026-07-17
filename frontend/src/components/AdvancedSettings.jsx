import { Link } from "react-router-dom";

const FIELD_LABELS = {
  movies_root: "Movies folder path",
  tv_root: "TV folder path",
  radarr_root_folder: "Radarr root folder",
  sonarr_root_folder: "Sonarr root folder",
  library_sync_interval_hours: "Auto-sync every (hours)",
  tv_page_size: "TV titles per sync page",
  library_enrich_workers: "Parallel enrich workers",
  library_sync_hour: "Preferred sync hour",
};

const FIELD_HELP = {
  movies_root: "Host path Radarr uses for movies (usually matches Radarr).",
  tv_root: "Host path Sonarr uses for TV (usually matches Sonarr).",
  library_enrich_workers: "Titles enriched in parallel during sync. Lower if the host feels busy.",
};

const DISK_PATH_FIELDS = ["movies_root", "tv_root", "radarr_root_folder", "sonarr_root_folder"];
const SYNC_FIELDS = ["library_sync_interval_hours", "tv_page_size", "library_enrich_workers"];

function fieldLabel(key) {
  return FIELD_LABELS[key] || key.replace(/_/g, " ");
}

function InlineAlert({ type, message }) {
  if (!message || (type !== "success" && type !== "error")) return null;
  return (
    <div className={`inline-alert inline-alert-${type}`} role="alert">
      {message}
    </div>
  );
}

function parseNumericSetting(key, raw) {
  if (key.endsWith("_hours") || key === "tv_page_size" || key === "library_enrich_workers") {
    return Number(raw || 0);
  }
  return raw;
}

function McpKeyRow({
  which,
  settings,
  revealed,
  busy,
  onRotate,
  onClear,
  onCopy,
}) {
  const field = which === "privacy" ? "mcp_api_key" : "mcp_full_api_key";
  const envName = which === "privacy" ? "CURATORX_MCP_API_KEY" : "CURATORX_MCP_FULL_API_KEY";
  const title = which === "privacy" ? "Privacy MCP key" : "Full MCP key";
  const description =
    which === "privacy"
      ? "Limited apps — public schema, read-only tools."
      : "Trusted in-stack — internal fields + confirm-gated *arr tools.";
  const configured = Boolean(settings?.[`${field}_set`]);
  const hint = settings?.[`${field}_hint`] || "";
  const source = settings?.[`${field}_source`] || "";
  const rotating = busy === `rotate-${which}`;
  const clearing = busy === `clear-${which}`;

  return (
    <article className="mcp-key-row" data-testid={`mcp-key-${which}`}>
      <div className="mcp-key-row-body">
        <div className="mcp-key-row-title">
          <h3>{title}</h3>
          <span
            className={`config-badge ${configured ? "config-badge-ok" : "config-badge-muted"}`}
            data-testid={`mcp-key-${which}-status`}
          >
            {configured ? "Set" : "Not set"}
          </span>
          <code className="mcp-key-env-chip">{envName}</code>
        </div>
        <p className="mcp-key-desc">{description}</p>
        {configured ? (
          <p className="mcp-key-meta">
            {hint ? (
              <>
                Key ends with <code>{hint}</code>
              </>
            ) : (
              "Key configured."
            )}
            {source ? ` · Source: ${source}` : null}
          </p>
        ) : (
          <p className="mcp-key-meta">HTTP /mcp stays disabled for this mode until a key is set.</p>
        )}
        {revealed ? (
          <label className="mcp-key-reveal">
            <span>New key (copy now)</span>
            <div className="mcp-key-reveal-row">
              <input type="text" readOnly value={revealed} data-testid={`mcp-key-${which}-revealed`} />
              <button type="button" className="ghost" onClick={onCopy}>
                Copy
              </button>
            </div>
          </label>
        ) : null}
      </div>
      <div className="mcp-key-row-actions">
        <button
          type="button"
          className="ghost"
          data-testid={`mcp-key-${which}-rotate`}
          disabled={Boolean(busy)}
          onClick={onRotate}
        >
          {rotating ? "Regenerating…" : configured ? "Regenerate" : "Generate"}
        </button>
        {configured && source !== "env" ? (
          <button
            type="button"
            className="ghost"
            data-testid={`mcp-key-${which}-clear`}
            disabled={Boolean(busy)}
            onClick={onClear}
          >
            {clearing ? "Clearing…" : "Clear"}
          </button>
        ) : null}
      </div>
    </article>
  );
}

export default function AdvancedSettings({
  settings,
  updateSettings,
  onSavePathsAndSync,
  onRotateMcpKey,
  onClearMcpKey,
  onCopyMcpKey,
  mcpRevealedKeys,
  mcpKeyBusy,
  saveAlert,
  mcpAlert,
}) {
  return (
    <div className="advanced-settings" data-testid="advanced-settings">
      <div className="advanced-settings-group" data-testid="advanced-paths-sync">
        <section className="config-panel">
          <header className="config-panel-header">
            <h2>Disk paths</h2>
            <p className="config-panel-lead">
              Host folder paths for Radarr and Sonarr. Most installs can leave these as-is.
            </p>
          </header>
          <div className="config-grid config-grid-2col">
            {DISK_PATH_FIELDS.map((key) => (
              <label key={key} className="config-form-field">
                <span>{fieldLabel(key)}</span>
                <input
                  type="text"
                  value={settings[key] ?? ""}
                  onChange={(event) =>
                    updateSettings({ [key]: parseNumericSetting(key, event.target.value) })
                  }
                />
                {FIELD_HELP[key] ? <span className="field-help">{FIELD_HELP[key]}</span> : null}
              </label>
            ))}
          </div>
        </section>

        <section className="config-panel">
          <header className="config-panel-header">
            <h2>Sync schedule &amp; performance</h2>
            <p className="config-panel-lead">
              Control automatic library refresh timing and how hard sync runs on your host.
            </p>
          </header>
          <div className="config-grid config-grid-2col">
            {SYNC_FIELDS.map((key) => (
              <label key={key} className="config-form-field">
                <span>{fieldLabel(key)}</span>
                <input
                  type="text"
                  value={settings[key] ?? ""}
                  onChange={(event) =>
                    updateSettings({ [key]: parseNumericSetting(key, event.target.value) })
                  }
                />
                {FIELD_HELP[key] ? <span className="field-help">{FIELD_HELP[key]}</span> : null}
              </label>
            ))}
            <label className="config-form-field">
              <span>{fieldLabel("library_sync_hour")}</span>
              <select
                data-testid="library-sync-hour"
                value={
                  settings.library_sync_hour === null || settings.library_sync_hour === undefined
                    ? ""
                    : String(settings.library_sync_hour)
                }
                onChange={(event) => {
                  const raw = event.target.value;
                  updateSettings({
                    library_sync_hour: raw === "" ? null : Number(raw),
                  });
                }}
              >
                <option value="">Any time (interval only)</option>
                {Array.from({ length: 24 }, (_, hour) => (
                  <option key={hour} value={hour}>
                    {String(hour).padStart(2, "0")}:00 (local)
                  </option>
                ))}
              </select>
              <span className="field-help">
                Uses the container clock. Set <code>TZ</code> on Unraid if the hour looks wrong.
              </span>
            </label>
          </div>
          <footer className="config-panel-footer">
            <button type="button" data-testid="advanced-paths-sync-save" onClick={onSavePathsAndSync}>
              Save paths &amp; sync
            </button>
            <InlineAlert type={saveAlert?.type} message={saveAlert?.message} />
          </footer>
        </section>
      </div>

      <section className="config-panel" data-testid="advanced-mcp">
        <header className="config-panel-header">
          <h2>MCP (Model Context Protocol)</h2>
          <p className="config-panel-lead">
            Dual-mode HTTP endpoint at <code>/mcp</code>. Send{" "}
            <code>X-CuratorX-MCP-Key</code> or Bearer auth. Keys must differ. Regenerating writes{" "}
            <code>settings.json</code>. See{" "}
            <Link to="/privacy">Privacy</Link> for exposure details.
          </p>
        </header>
        <div className="mcp-key-list">
          <McpKeyRow
            which="privacy"
            settings={settings}
            revealed={mcpRevealedKeys.privacy || ""}
            busy={mcpKeyBusy}
            onRotate={() => onRotateMcpKey("privacy")}
            onClear={() => onClearMcpKey("privacy")}
            onCopy={() => onCopyMcpKey("privacy")}
          />
          <McpKeyRow
            which="full"
            settings={settings}
            revealed={mcpRevealedKeys.full || ""}
            busy={mcpKeyBusy}
            onRotate={() => onRotateMcpKey("full")}
            onClear={() => onClearMcpKey("full")}
            onCopy={() => onCopyMcpKey("full")}
          />
        </div>
        <InlineAlert type={mcpAlert?.type} message={mcpAlert?.message} />
      </section>
    </div>
  );
}

import InlineAlert from "../../components/InlineAlert";

/**
 * Admin Seerr section — Overseerr / Jellyseerr request routing.
 * Extracted from ConfigPage (H1 remaining carve after Household/Libraries).
 */

type SettingsBag = any; // ConfigPage settings blob until Wave 4

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


/** Props for SeerrSection. */
type SeerrSectionProps = { [key: string]: any }; // Admin section bags until Wave 4

export default function SeerrSection({
  settings,
  persistSettings,
  updateFeatureFlags,
  updateSeerrSettings,
  testing,
  testResults,
  certifications,
  runTest,
  actionAlert,
  setActionFeedback,
  CertifiedBadge,
  renderSeerrSecretInput,
}: SeerrSectionProps) {
  return (
    <section className="config-section" data-testid="seerr-settings">
      <h2>Overseerr / Seerr (optional)</h2>
      <p className="wizard-note">
        Let household members request titles through Overseerr or Jellyseerr instead of managing Radarr/Sonarr directly.
      </p>
      <label className="config-toggle" data-testid="seerr-enabled-toggle">
        <input
          type="checkbox"
          checked={Boolean(settings?.features?.seerr_enabled)}
          onChange={(event) => {
            const enabled = event.target.checked;
            updateFeatureFlags({ seerr_enabled: enabled });
            persistSettings({
              features: { ...(settings.features || {}), seerr_enabled: enabled },
            })
              .then(() =>
                setActionFeedback?.(
                  "seerr",
                  "success",
                  enabled ? "Seerr requests enabled." : "Seerr requests disabled.",
                ),
              )
              .catch((error: any) => setActionFeedback?.("seerr", "error", (error as { message?: string }).message));
          }}
        />
        <span>Route household requests through Seerr</span>
      </label>
      <div className={`service-card ${testResults.seerr?.state === "success" ? "service-ok" : ""} ${testing === "seerr" ? "service-loading" : ""} ${testResults.seerr?.state === "error" ? "service-error" : ""}`}>
          <div className="service-card-header">
            <div className="service-card-title">
              <h3>Seerr server</h3>
              <CertifiedBadge
                certified={certifications.seerr?.certified}
                testing={testing === "seerr"}
                serviceId="seerr"
              />
            </div>
            <div className="service-card-actions">
              <button
                type="button"
                className="primary"
                data-testid="verify-seerr"
                onClick={() => runTest("seerr")}
                disabled={testing === "seerr"}
              >
                {testing === "seerr" ? "Testing…" : "Test connection"}
              </button>
            </div>
          </div>
          <div className="service-fields">
            <label>
              <span>Server URL</span>
              <input
                type="text"
                data-testid="seerr-url"
                value={settings?.seerr?.url ?? ""}
                placeholder="http://192.168.1.50:5055"
                onChange={(event) => updateSeerrSettings({ url: event.target.value })}
                onBlur={() =>
                  persistSettings({
                    seerr: { ...(settings.seerr || {}), url: settings?.seerr?.url ?? "" },
                  }).catch((error: any) => setActionFeedback?.("seerr", "error", (error as { message?: string }).message))
                }
              />
            </label>
            <label>
              <span>API key</span>
              {renderSeerrSecretInput({ disabled: testing === "seerr" })}
            </label>
          </div>
          <label className="config-toggle" data-testid="seerr-link-on-login">
            <input
              type="checkbox"
              checked={settings?.seerr?.link_on_login !== false}
              onChange={(event) => {
                const linkOnLogin = event.target.checked;
                updateSeerrSettings({ link_on_login: linkOnLogin });
                persistSettings({
                  seerr: { ...(settings.seerr || {}), link_on_login: linkOnLogin },
                }).catch((error: any) => setActionFeedback?.("seerr", "error", (error as { message?: string }).message));
              }}
            />
            <span>Match Plex users to Seerr accounts when they sign in</span>
          </label>
          <label className="config-toggle" data-testid="seerr-require-linked-user">
            <input
              type="checkbox"
              checked={Boolean(settings?.seerr?.require_linked_user_for_requests)}
              onChange={(event) => {
                const required = event.target.checked;
                updateSeerrSettings({ require_linked_user_for_requests: required });
                persistSettings({
                  seerr: {
                    ...(settings.seerr || {}),
                    require_linked_user_for_requests: required,
                  },
                }).catch((error: any) => setActionFeedback?.("seerr", "error", (error as { message?: string }).message));
              }}
            />
            <span>Only allow requests after a Seerr account is linked</span>
          </label>
          {testResults.seerr?.message ? (
            <InlineAlert
              type={actionAlert?.area === "seerr" ? actionAlert.type : testResults.seerr.state}
              message={actionAlert?.area === "seerr" ? actionAlert.message : testResults.seerr.message}
            />
          ) : null}
        </div>
    </section>
  );
}

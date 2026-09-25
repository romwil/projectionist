import InlineAlert from "../../components/InlineAlert";
import {
  LLM_MODEL_DEFAULTS,
  LLM_PROVIDER_DEFAULTS,
} from "../../api/client";
import { secretPlaceholder } from "../../lib/secretField.js";

/**
 * Admin Connections — LLM, Plex/Radarr/Sonarr, optional enrichments.
 * Extracted from ConfigPage (H1 remaining carve after Household/Libraries).
 */
export default function ConnectionsSection({
  settings,
  updateSettings,
  handleProviderChange,
  renderSecretInput,
  modelPickerOptions,
  modelCatalog,
  modelCatalogLoading,
  refreshModelCatalog,
  runTest,
  testing,
  certifications,
  testResults,
  actionAlert,
  CertifiedBadge,
  ProviderSelect,
  connectionStatusAlert,
  OPTIONAL_SERVICES,
  SECRET_FIELDS,
  FIELD_PLACEHOLDERS,
  FIELD_HELP,
  fieldLabel,
}) {
  return (
    <>
      <section className="config-section">
        <h2>Language model</h2>
        <p className="wizard-note">The AI that powers chat recommendations. Bring your own key or run Ollama locally.</p>
        <div className="connections-field-grid" data-testid="connections-llm-fields">
          <label>
            <span>Provider</span>
            <ProviderSelect
              value={settings.llm_provider}
              onChange={(event) => handleProviderChange(event.target.value)}
            />
          </label>
          <label>
            <span>API base URL</span>
            <input
              type="text"
              value={settings.llm_base_url ?? ""}
              onChange={(event) => updateSettings({ llm_base_url: event.target.value })}
              placeholder={LLM_PROVIDER_DEFAULTS[settings.llm_provider] || "https://api.openai.com/v1"}
            />
          </label>
          <label>
            <span>API key</span>
            {renderSecretInput("llm_api_key", {
              placeholder: secretPlaceholder(settings, "llm_api_key", "Required except for Ollama"),
            })}
          </label>
          <label>
            <span>Model name</span>
            <input
              type="text"
              list="llm-model-options-connections"
              value={settings.llm_model ?? ""}
              onChange={(event) => updateSettings({ llm_model: event.target.value })}
              placeholder={LLM_MODEL_DEFAULTS[settings.llm_provider] || "gpt-4o-mini"}
              data-testid="llm-model-input-llm-model-options-connections"
            />
            <datalist id="llm-model-options-connections">
              {modelPickerOptions().map((row) => (
                <option key={row.id} value={row.id}>
                  {row.hint === "cheaper-tier" ? "cheaper tier" : row.hint === "standard-tier" ? "standard" : ""}
                </option>
              ))}
            </datalist>
          </label>
        </div>
        {(() => {
          const options = modelPickerOptions();
          const cheaper = options.filter((row) => row.hint === "cheaper-tier").slice(0, 4);
          return (
            <>
              {cheaper.length ? (
                <div className="llm-cheaper-picks" data-testid="llm-cheaper-picks-llm-model-options-connections">
                  {cheaper.map((row) => (
                    <button
                      key={row.id}
                      type="button"
                      className="ghost"
                      onClick={() => updateSettings({ llm_model: row.id })}
                    >
                      {row.id}
                      <span className="llm-model-hint">cheaper</span>
                    </button>
                  ))}
                </div>
              ) : null}
              <p className="llm-model-catalog-note">
                {modelCatalogLoading
                  ? "Loading provider model list…"
                  : modelCatalog?.source === "pinned"
                    ? modelCatalog?.note || modelCatalog?.error || "Showing pinned model options."
                    : `Loaded ${options.length} models from ${modelCatalog?.source || "provider"}.`}
                {" "}
                <button type="button" className="ghost" onClick={() => refreshModelCatalog()} disabled={modelCatalogLoading}>
                  Refresh models
                </button>
              </p>
            </>
          );
        })()}
        <div className="connections-llm-actions">
          <button type="button" className="primary" onClick={() => runTest("llm")} disabled={testing === "llm"}>
            Test connection
          </button>
          <CertifiedBadge certified={certifications.llm?.certified} testing={testing === "llm"} serviceId="llm" />
        </div>
        {(() => {
          const alert = connectionStatusAlert(
            actionAlert,
            "llm",
            testResults.llm,
            certifications.llm?.certified,
          );
          return <InlineAlert type={alert.type} message={alert.message} />;
        })()}
      </section>

      <section className="config-section">
        <h2>Plex, Radarr &amp; Sonarr</h2>
        <p className="wizard-note">
          Library and download stack. Plex is required; Radarr and Sonarr unlock add/remove after you confirm in chat.
        </p>
        <div className="service-cards">
          {[
            { id: "plex", label: "Plex", fields: ["plex_url", "plex_token"] },
            { id: "radarr", label: "Radarr", fields: ["radarr_url", "radarr_api_key"] },
            { id: "sonarr", label: "Sonarr", fields: ["sonarr_url", "sonarr_api_key"] },
          ].map(({ id, label, fields }) => {
            const result = testResults[id];
            return (
              <div key={id} className={`service-card ${result?.state === "success" ? "service-ok" : ""} ${testing === id ? "service-loading" : ""} ${result?.state === "error" ? "service-error" : ""}`}>
                <div className="service-card-header">
                  <div className="service-card-title">
                    <h3>{label}</h3>
                    <CertifiedBadge
                      certified={certifications[id]?.certified}
                      testing={testing === id}
                      serviceId={id}
                    />
                  </div>
                  <div className="service-card-actions">
                    <button type="button" className="primary" onClick={() => runTest(id)} disabled={testing === id}>
                      {testing === id ? "Testing…" : "Test"}
                    </button>
                  </div>
                </div>
                <div className="service-fields">
                  {fields.map((field) => (
                    <label key={field}>
                      <span>{fieldLabel(field)}</span>
                      {SECRET_FIELDS.includes(field) ? (
                        renderSecretInput(field, { placeholder: FIELD_PLACEHOLDERS[field] })
                      ) : (
                        <input
                          type="text"
                          value={settings[field] ?? ""}
                          placeholder={FIELD_PLACEHOLDERS[field] || ""}
                          onChange={(event) => updateSettings({ [field]: event.target.value })}
                        />
                      )}
                      {FIELD_HELP[field] ? (
                        <span className="wizard-note field-help">{FIELD_HELP[field]}</span>
                      ) : null}
                    </label>
                  ))}
                </div>
                {(() => {
                  const alert = connectionStatusAlert(
                    actionAlert,
                    id,
                    result,
                    certifications[id]?.certified,
                  );
                  return alert.message ? (
                    <InlineAlert
                      type={alert.type}
                      message={alert.message}
                    />
                  ) : null;
                })()}
              </div>
            );
          })}
        </div>
      </section>

      <section className="config-section">
        <h2>Optional enrichments</h2>
        <p className="wizard-note">
          TMDB improves discovery and artwork. Wikipedia research is available without a key; OMDb and TVDB are optional
          research sources. Fanart.tv and Tautulli are optional extras.
        </p>
        <div className="service-cards">
          {OPTIONAL_SERVICES.map(({ id, label, fields }) => {
            const result = testResults[id];
            return (
              <div key={id} className={`service-card ${result?.state === "success" ? "service-ok" : ""} ${testing === id ? "service-loading" : ""} ${result?.state === "error" ? "service-error" : ""}`}>
                <div className="service-card-header">
                  <div className="service-card-title">
                    <h3>{label}</h3>
                    <CertifiedBadge
                      certified={certifications[id]?.certified}
                      testing={testing === id}
                      serviceId={id}
                    />
                  </div>
                  <div className="service-card-actions">
                    <button type="button" className="primary" onClick={() => runTest(id)} disabled={testing === id}>
                      {testing === id ? "Testing…" : "Test"}
                    </button>
                  </div>
                </div>
                <div className="service-fields">
                  {fields.map((field) => (
                    <label key={field}>
                      <span>{fieldLabel(field)}</span>
                      {SECRET_FIELDS.includes(field) ? (
                        renderSecretInput(field, { placeholder: FIELD_PLACEHOLDERS[field] })
                      ) : (
                        <input
                          type="text"
                          value={settings[field] ?? ""}
                          placeholder={FIELD_PLACEHOLDERS[field] || ""}
                          onChange={(event) => updateSettings({ [field]: event.target.value })}
                        />
                      )}
                      {FIELD_HELP[field] ? (
                        <span className="wizard-note field-help">{FIELD_HELP[field]}</span>
                      ) : null}
                    </label>
                  ))}
                </div>
                {(() => {
                  const alert = connectionStatusAlert(
                    actionAlert,
                    id,
                    result,
                    certifications[id]?.certified,
                  );
                  return alert.message ? (
                    <InlineAlert
                      type={alert.type}
                      message={alert.message}
                    />
                  ) : null;
                })()}
              </div>
            );
          })}
        </div>
        <p className="wizard-note" data-testid="research-source-readiness">
          Chat research sources: TMDB {settings.tmdb_api_key_set ? "configured" : "needs an API key"} · Wikipedia available
          without a key · OMDb {settings.omdb_api_key_set ? "configured" : "optional (API key)"} · TVDB{" "}
          {settings.tvdb_api_key_set ? "configured" : "optional (v4 API key/subscription)"}.
        </p>
        <div className="service-fields">
          <label>
            <span>OMDb API key (optional)</span>
            {renderSecretInput("omdb_api_key", {
              placeholder: secretPlaceholder(settings, "omdb_api_key", "Optional IMDb-aligned research"),
            })}
          </label>
          <label>
            <span>TVDB API key (optional)</span>
            {renderSecretInput("tvdb_api_key", {
              placeholder: secretPlaceholder(settings, "tvdb_api_key", "Optional TVDB v4 key"),
            })}
          </label>
        </div>
      </section>
    </>
  );
}

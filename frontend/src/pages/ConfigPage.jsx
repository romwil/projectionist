import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AUTO_CERTIFY_SERVICES,
  ANTHROPIC_MODEL_OPTIONS,
  LLM_MODEL_DEFAULTS,
  LLM_PROVIDER_DEFAULTS,
  LLM_PROVIDER_OPTIONS,
  WIZARD_STEPS,
  api,
  getAuthMe,
  getFeatures,
  getPersona,
  getSettings,
  getWizardStatus,
  getPlexSections,
  listJobs,
  listUsers,
  putPersona,
  putSystemConfig,
  resolveModelForProvider,
  saveSettings,
  testService,
  updateUserRole,
} from "../api/client";
import PersonaSection from "../components/PersonaSection";
import {
  formatLastSyncRelative,
  formatSyncJobDetails,
} from "../lib/jobProgress.js";

const SECRET_FIELDS = [
  "plex_token",
  "radarr_api_key",
  "sonarr_api_key",
  "tmdb_api_key",
  "tvdb_api_key",
  "fanart_api_key",
  "tautulli_api_key",
  "llm_api_key",
  "seerr_api_key",
];

function seerrSecretPlaceholder(settings, fallback = "") {
  if (settings?.seerr?.api_key_set) {
    return "Configured (leave blank to keep)";
  }
  return fallback;
}

function settingsPayloadForTest(service, settings) {
  if (service !== "seerr") return settings;
  return {
    ...settings,
    seerr_url: settings.seerr?.url || "",
    seerr_api_key: settings.seerr?.api_key || "",
  };
}

function secretPlaceholder(settings, field, fallback = "") {
  if (settings?.[`${field}_source`] === "env") {
    return "Configured via environment (.env)";
  }
  if (settings?.[`${field}_set`]) {
    return "Configured (leave blank to keep)";
  }
  return fallback;
}

function SecretInput({
  field,
  settings,
  value,
  onChange,
  disabled = false,
  placeholder = "",
  visible = false,
  onToggleVisible,
}) {
  return (
    <div className="secret-field">
      <input
        type={visible ? "text" : "password"}
        value={value ?? ""}
        disabled={disabled}
        placeholder={placeholder || secretPlaceholder(settings, field)}
        onChange={onChange}
        autoComplete="off"
      />
      <button
        type="button"
        className="secret-toggle"
        data-testid={`secret-toggle-${field}`}
        aria-label={visible ? "Hide secret" : "Show secret"}
        aria-pressed={visible}
        disabled={disabled}
        onClick={onToggleVisible}
      >
        {visible ? "Hide" : "Show"}
      </button>
    </div>
  );
}

function InlineAlert({ type, message, testId }) {
  if (!message || (type !== "success" && type !== "error")) return null;
  return (
    <div
      className={`inline-alert inline-alert-${type}`}
      role="alert"
      data-testid={testId || `inline-alert-${type}`}
    >
      {message}
    </div>
  );
}

function CertifiedBadge({ certified, testing, serviceId }) {
  if (testing) {
    return (
      <span className="certified-badge certified-badge-testing" data-testid={`certified-badge-${serviceId}`}>
        Testing…
      </span>
    );
  }
  if (certified) {
    return (
      <span className="certified-badge certified-badge-ok" data-testid={`certified-badge-${serviceId}`}>
        Certified ✓
      </span>
    );
  }
  return (
    <span className="certified-badge certified-badge-pending" data-testid={`certified-badge-${serviceId}`}>
      Uncertified
    </span>
  );
}

function serviceCredentialsPresent(service, settings) {
  if (!settings) return false;
  switch (service) {
    case "llm":
      return Boolean(
        settings.llm_model &&
          (settings.llm_provider === "ollama" || settings.llm_api_key_set),
      );
    case "plex":
      return Boolean(settings.plex_url && settings.plex_token_set);
    case "radarr":
      return Boolean(settings.radarr_url && settings.radarr_api_key_set);
    case "sonarr":
      return Boolean(settings.sonarr_url && settings.sonarr_api_key_set);
    case "tmdb":
      return Boolean(settings.tmdb_api_key_set);
    case "fanart":
      return Boolean(settings.fanart_api_key_set);
    case "tautulli":
      return Boolean(settings.tautulli_url && settings.tautulli_api_key_set);
    case "seerr":
      return Boolean(settings.seerr?.url && settings.seerr?.api_key_set);
    default:
      return false;
  }
}

function ProviderSelect({ value, onChange }) {
  return (
    <select value={value || "openai"} onChange={onChange}>
      {LLM_PROVIDER_OPTIONS.map(({ value: providerValue, label }) => (
        <option key={providerValue} value={providerValue}>
          {label}
        </option>
      ))}
    </select>
  );
}

const STEP_LABELS = {
  identity_seed: "Identity Seed",
  infrastructure: "Infrastructure",
  dropdown_mapping: "Library Mapping",
};

const INFRASTRUCTURE_SERVICES = [
  { id: "llm", label: "LLM Engine", kind: "llm" },
  { id: "plex", label: "Plex", kind: "plex", fields: ["plex_url", "plex_token"] },
  { id: "radarr", label: "Radarr", kind: "service", fields: ["radarr_url", "radarr_api_key"] },
  { id: "sonarr", label: "Sonarr", kind: "service", fields: ["sonarr_url", "sonarr_api_key"] },
];

const OPTIONAL_SERVICES = [
  { id: "tmdb", label: "TMDB", fields: ["tmdb_api_key"] },
  { id: "fanart", label: "Fanart.tv", fields: ["fanart_api_key"] },
  { id: "tautulli", label: "Tautulli", fields: ["tautulli_url", "tautulli_api_key"] },
];

function wizardPersonaPreview(persona) {
  if (!persona) return "";
  if (persona.assembled_prompt) return persona.assembled_prompt;
  return `Hello, I'm ${persona.curator_name}. I'll curate your library with a balanced voice.`;
}

function stepUnlocked(stepIndex, verification) {
  if (stepIndex === 0) return true;
  if (stepIndex === 1) return verification.identity;
  if (stepIndex === 2) return verification.identity && verification.plex;
  return false;
}

function canAdvance(stepIndex, verification) {
  if (stepIndex === 0) return verification.identity;
  if (stepIndex === 1) {
    return verification.llm && verification.plex && verification.radarr && verification.sonarr;
  }
  if (stepIndex === 2) return verification.sections;
  return false;
}

function onboardingReady(verification) {
  return (
    verification.identity &&
    verification.llm &&
    verification.plex &&
    verification.sections &&
    verification.radarr &&
    verification.sonarr
  );
}

function firstIncompleteWizardStep(wizardData) {
  const steps = wizardData?.steps;
  if (!steps) return 0;
  if (!steps.identity_seed?.complete) return 0;
  if (!steps.infrastructure?.complete) return 1;
  return 2;
}

export default function ConfigPage() {
  const navigate = useNavigate();
  const [settings, setSettings] = useState(null);
  const [persona, setPersona] = useState(null);
  const [wizard, setWizard] = useState(null);
  const [status, setStatus] = useState("");
  const [actionAlert, setActionAlert] = useState(null);
  const [footerAlert, setFooterAlert] = useState(null);
  const [sections, setSections] = useState([]);
  const [testing, setTesting] = useState(null);
  const [testResults, setTestResults] = useState({});
  const [certifications, setCertifications] = useState({});
  const [autoCertifying, setAutoCertifying] = useState(false);
  const [autoCertifyDone, setAutoCertifyDone] = useState(false);
  const [verification, setVerification] = useState({
    identity: false,
    llm: false,
    plex: false,
    sections: false,
    radarr: false,
    sonarr: false,
  });
  const [stepIndex, setStepIndex] = useState(0);
  const [showWizard, setShowWizard] = useState(true);
  const [onboardingHints, setOnboardingHints] = useState([]);
  const [savingPersona, setSavingPersona] = useState(false);
  const [plexCollapsed, setPlexCollapsed] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [visibleSecrets, setVisibleSecrets] = useState({});
  const [libraryStats, setLibraryStats] = useState(null);
  const [libraryHealth, setLibraryHealth] = useState(null);
  const [exportingCorpus, setExportingCorpus] = useState(false);
  const [syncingLibrary, setSyncingLibrary] = useState(false);
  const [activeSyncJob, setActiveSyncJob] = useState(null);
  const [featureFlags, setFeatureFlags] = useState(null);
  const [managedUsers, setManagedUsers] = useState([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const trackedSyncJobIdRef = useRef(null);
  const syncWasRunningRef = useRef(false);

  const preview = useMemo(() => wizardPersonaPreview(persona), [persona]);
  const movieSections = useMemo(() => sections.filter((s) => s.type === "movie"), [sections]);
  const tvSections = useMemo(() => sections.filter((s) => s.type === "show"), [sections]);

  function applyCertifications(certMap) {
    setCertifications(certMap || {});
    const initialResults = {};
    for (const [service, cert] of Object.entries(certMap || {})) {
      if (cert?.certified) {
        initialResults[service] = { state: "success", message: "Certified" };
      }
    }
    if (Object.keys(initialResults).length) {
      setTestResults((prev) => ({ ...initialResults, ...prev }));
    }
    setVerification((prev) => ({
      ...prev,
      llm: certMap?.llm?.certified || prev.llm,
      plex: certMap?.plex?.certified || prev.plex,
      radarr: certMap?.radarr?.certified || prev.radarr,
      sonarr: certMap?.sonarr?.certified || prev.sonarr,
    }));
  }

  async function refreshWizard() {
    const wizardData = await getWizardStatus();
    setWizard(wizardData);
    if (wizardData.certifications) {
      applyCertifications(wizardData.certifications);
    }
    if (wizardData.onboarding_complete) {
      setShowWizard(false);
    }
    setVerification((prev) => ({
      ...prev,
      identity: wizardData.steps.identity_seed.curator_name_set || prev.identity,
      llm: wizardData.steps.infrastructure.llm_verified || prev.llm,
      plex: wizardData.steps.infrastructure.plex_verified || prev.plex,
      sections: wizardData.steps.dropdown_mapping.sections_set || prev.sections,
      radarr: wizardData.steps.infrastructure.radarr_verified || prev.radarr,
      sonarr: wizardData.steps.infrastructure.sonarr_verified || prev.sonarr,
    }));
    if (!wizardData.onboarding_complete) {
      setStepIndex(firstIncompleteWizardStep(wizardData));
    }
  }

  useEffect(() => {
    Promise.all([getSettings(), getPersona(), getWizardStatus()]).then(
      ([settingsData, personaData, wizardData]) => {
        const normalizedModel = resolveModelForProvider(
          settingsData.llm_provider,
          settingsData.llm_model,
        );
        setSettings(
          normalizedModel === settingsData.llm_model
            ? settingsData
            : { ...settingsData, llm_model: normalizedModel },
        );
        setPersona(personaData);
        setWizard(wizardData);
        setShowWizard(!wizardData.onboarding_complete);
        if (wizardData.certifications) {
          applyCertifications(wizardData.certifications);
        }
        setVerification({
          identity: wizardData.steps.identity_seed.curator_name_set,
          llm: wizardData.certifications?.llm?.certified || wizardData.steps.infrastructure.llm_verified,
          plex: wizardData.certifications?.plex?.certified || wizardData.steps.infrastructure.plex_verified,
          sections: wizardData.steps.dropdown_mapping.sections_set,
          radarr: wizardData.certifications?.radarr?.certified || wizardData.steps.infrastructure.radarr_verified,
          sonarr: wizardData.certifications?.sonarr?.certified || wizardData.steps.infrastructure.sonarr_verified,
        });
        if (wizardData.steps.infrastructure.plex_verified || wizardData.certifications?.plex?.certified) {
          setPlexCollapsed(true);
        }
        if (!wizardData.onboarding_complete) {
          setStepIndex(firstIncompleteWizardStep(wizardData));
        }
      },
    );
    getFeatures()
      .then((data) => setFeatureFlags(data))
      .catch(() => setFeatureFlags(null));
  }, []);

  useEffect(() => {
    if (!settings) return;
    refreshManagedUsers().catch(() => {});
  }, [settings?.features?.multi_user_enabled]);

  useEffect(() => {
    if (!settings || autoCertifyDone || autoCertifying) return;

    const pending = AUTO_CERTIFY_SERVICES.filter(
      (service) =>
        !certifications[service]?.certified && serviceCredentialsPresent(service, settings),
    );
    if (!pending.length) {
      setAutoCertifyDone(true);
      return;
    }

    let cancelled = false;

    async function autoCertify() {
      setAutoCertifying(true);
      for (const service of pending) {
        if (cancelled) break;
        await runTest(service, { silent: true });
        await new Promise((resolve) => setTimeout(resolve, 300));
      }
      if (!cancelled) {
        setAutoCertifyDone(true);
        setAutoCertifying(false);
      }
    }

    autoCertify();
    return () => {
      cancelled = true;
    };
  }, [settings, certifications, autoCertifyDone, autoCertifying]);

  useEffect(() => {
    if (!settings) return;
    const sectionsSet = Boolean(settings.plex_movie_section && settings.plex_tv_section);
    setVerification((prev) => ({ ...prev, sections: sectionsSet || prev.sections }));
  }, [settings?.plex_movie_section, settings?.plex_tv_section]);

  useEffect(() => {
    if (!persona) return;
    setVerification((prev) => ({
      ...prev,
      identity: Boolean(String(persona.curator_name || "").trim()) || prev.identity,
    }));
  }, [persona?.curator_name]);

  useEffect(() => {
    if (!settings || sections.length) return;
    if (!serviceCredentialsPresent("plex", settings) && !verification.plex) return;
    getPlexSections()
      .then((loaded) => setSections(loaded))
      .catch(() => {});
  }, [settings, verification.plex, sections.length]);

  useEffect(() => {
    if (showWizard) return;
    api("/library/stats")
      .then(setLibraryStats)
      .catch(() => setLibraryStats(null));
    api("/library/health")
      .then(setLibraryHealth)
      .catch(() => setLibraryHealth(null));
  }, [showWizard]);

  useEffect(() => {
    if (showWizard) return undefined;

    let cancelled = false;

    async function pollSyncJobs() {
      try {
        const jobs = await listJobs();
        if (cancelled) return;
        const syncJobs = jobs.filter((job) => job.job_type === "library_sync");
        const running = syncJobs.find((job) => job.status === "running" || job.status === "queued");
        const trackedId = trackedSyncJobIdRef.current;
        const tracked =
          (trackedId && syncJobs.find((job) => job.id === trackedId)) || syncJobs[0] || null;
        const active = running || tracked;
        setActiveSyncJob(active);
        const isRunning = Boolean(running);
        setSyncingLibrary(isRunning);
        if (syncWasRunningRef.current && !isRunning && active?.status === "completed") {
          api("/library/stats")
            .then(setLibraryStats)
            .catch(() => {});
          api("/library/health")
            .then(setLibraryHealth)
            .catch(() => {});
        }
        syncWasRunningRef.current = isRunning;
      } catch {
        if (!cancelled) setSyncingLibrary(false);
      }
    }

    pollSyncJobs();
    // Poll at a fixed 2s while Config is open. Do not depend on syncingLibrary —
    // setSyncingLibrary inside this effect would re-run it and stack intervals.
    const interval = setInterval(pollSyncJobs, 2000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [showWizard]);

  function updateSettings(patch) {
    setSettings((prev) => ({ ...prev, ...patch }));
  }

  function updateFeatureFlags(patch) {
    setSettings((prev) => ({
      ...prev,
      features: { ...(prev?.features || {}), ...patch },
    }));
  }

  function updateAuthSettings(patch) {
    setSettings((prev) => ({
      ...prev,
      auth: { ...(prev?.auth || {}), ...patch },
    }));
  }

  function updateSeerrSettings(patch) {
    setSettings((prev) => ({
      ...prev,
      seerr: { ...(prev?.seerr || {}), ...patch },
    }));
  }

  async function refreshManagedUsers() {
    if (!settings?.features?.multi_user_enabled) {
      setManagedUsers([]);
      return;
    }
    try {
      const me = await getAuthMe();
      if (me?.user?.role !== "owner") {
        setManagedUsers([]);
        return;
      }
      setUsersLoading(true);
      const data = await listUsers();
      setManagedUsers(data.items || []);
    } catch {
      setManagedUsers([]);
    } finally {
      setUsersLoading(false);
    }
  }

  async function handleUserRoleChange(userId, role) {
    try {
      await updateUserRole(userId, role);
      await refreshManagedUsers();
      setActionFeedback("users", "success", "User role updated.");
    } catch (error) {
      setActionFeedback("users", "error", error.message);
    }
  }

  function renderSeerrSecretInput(options = {}) {
    const field = "seerr.api_key";
    const value = settings?.seerr?.api_key ?? "";
    const configured = Boolean(settings?.seerr?.api_key_set);
    return (
      <SecretInput
        field={field}
        settings={settings}
        value={value}
        disabled={options.disabled}
        placeholder={configured ? "Configured (leave blank to keep)" : ""}
        visible={Boolean(visibleSecrets[field])}
        onToggleVisible={() => toggleSecretVisibility(field)}
        onChange={(event) => updateSeerrSettings({ api_key: event.target.value })}
      />
    );
  }

  function toggleSecretVisibility(field) {
    setVisibleSecrets((prev) => ({ ...prev, [field]: !prev[field] }));
  }

  function renderSecretInput(field, options = {}) {
    return (
      <SecretInput
        field={field}
        settings={settings}
        value={settings[field] ?? ""}
        disabled={options.disabled}
        placeholder={options.placeholder}
        visible={Boolean(visibleSecrets[field])}
        onToggleVisible={() => toggleSecretVisibility(field)}
        onChange={(event) => updateSettings({ [field]: event.target.value })}
      />
    );
  }

  function setActionFeedback(area, type, message) {
    setActionAlert({ area, type, message });
    setStatus(message);
  }

  function clearActionFeedback(area) {
    setActionAlert((prev) => (prev?.area === area ? null : prev));
  }

  function llmSettingsPatch(overrides = {}) {
    const patch = {
      llm_provider: overrides.llm_provider ?? settings.llm_provider,
      llm_base_url: overrides.llm_base_url ?? settings.llm_base_url,
      llm_model: overrides.llm_model ?? settings.llm_model,
    };
    const apiKey = overrides.llm_api_key ?? settings.llm_api_key;
    if (String(apiKey || "").trim()) {
      patch.llm_api_key = apiKey;
    }
    return patch;
  }

  async function persistLlmSettings(overrides = {}, options = {}) {
    return persistSettings(llmSettingsPatch(overrides), options);
  }

  function handleProviderChange(provider) {
    const defaultUrl = LLM_PROVIDER_DEFAULTS[provider] ?? "";
    const nextModel = resolveModelForProvider(provider, settings.llm_model);
    updateSettings({
      llm_provider: provider,
      llm_base_url: defaultUrl,
      llm_model: nextModel,
    });
    clearActionFeedback("llm");
    setCertifications((prev) => ({
      ...prev,
      llm: { ...(prev.llm || {}), certified: false, connection_status: "unverified" },
    }));
    persistLlmSettings({
      llm_provider: provider,
      llm_base_url: defaultUrl,
      llm_model: nextModel,
    }).catch((error) => {
      setActionFeedback("llm", "error", error.message);
    });
  }

  async function persistSettings(patch = {}, options = {}) {
    const payload = { ...settings, ...patch };
    const saved = await saveSettings(payload);
    setSettings({ ...payload, ...saved });
    if (options.refreshWizard) await refreshWizard();
    return saved;
  }

  async function savePersonaField(field, value) {
    setSavingPersona(true);
    try {
      const updated = await putPersona({ [field]: value });
      setPersona(updated);
      if (field === "curator_name") {
        await putSystemConfig({ curator_name: String(value) });
        setVerification((prev) => ({
          ...prev,
          identity: Boolean(String(value || "").trim()),
        }));
      }
      setActionFeedback("persona", "success", "Persona updated.");
    } catch (error) {
      setActionFeedback("persona", "error", error.message);
    } finally {
      setSavingPersona(false);
    }
  }

  async function handleSyncReviewsToggle(enabled) {
    updateSettings({ sync_reviews_to_plex: enabled });
    try {
      await persistSettings({ sync_reviews_to_plex: enabled });
      setActionFeedback(
        "plex-sections",
        "success",
        enabled ? "Plex rating sync enabled." : "Plex rating sync disabled.",
      );
    } catch (error) {
      setActionFeedback("plex-sections", "error", error.message);
    }
  }

  async function handlePlexCollectionsToggle(enabled) {
    updateFeatureFlags({ plex_collections_enabled: enabled });
    try {
      await persistSettings({
        features: { ...(settings.features || {}), plex_collections_enabled: enabled },
      });
      setActionFeedback(
        "plex-sections",
        "success",
        enabled ? "Plex collection management enabled." : "Plex collection management disabled.",
      );
    } catch (error) {
      setActionFeedback("plex-sections", "error", error.message);
    }
  }

  async function handleSectionChange(field, value) {
    const nextMovie = field === "plex_movie_section" ? value : settings.plex_movie_section;
    const nextTv = field === "plex_tv_section" ? value : settings.plex_tv_section;
    updateSettings({ [field]: value });
    try {
      await persistSettings({ [field]: value });
      setVerification((prev) => ({
        ...prev,
        sections: Boolean(nextMovie && nextTv),
      }));
    } catch (error) {
      setActionFeedback("plex-sections", "error", error.message);
    }
  }

  async function runTest(service, options = {}) {
    const { silent = false } = options;
    setTesting(service);
    setTestResults((prev) => ({ ...prev, [service]: { state: "loading" } }));
    if (!silent) clearActionFeedback(service);
    try {
      const result = await testService(service, settingsPayloadForTest(service, settings));
      setTestResults((prev) => ({
        ...prev,
        [service]: {
          state: result.ok ? "success" : "error",
          message: result.message,
          version: result.version,
          movie_count: result.movie_count,
          series_count: result.series_count,
        },
      }));
      if (!silent) {
        setActionFeedback(service, result.ok ? "success" : "error", result.message);
      }
      if (result.sections) {
        setSections(result.sections);
        setPlexCollapsed(true);
      }
      if (result.hints) setOnboardingHints(result.hints);
      else if (result.hint) setOnboardingHints([result.hint]);

      setCertifications((prev) => ({
        ...prev,
        [service]: {
          ...(prev[service] || {}),
          certified: Boolean(result.ok),
          connection_status: result.ok ? "verified" : "failed",
        },
      }));

      if (result.ok) {
        const keyMap = {
          llm: "llm",
          plex: "plex",
          radarr: "radarr",
          sonarr: "sonarr",
        };
        if (keyMap[service]) {
          setVerification((prev) => ({ ...prev, [keyMap[service]]: true }));
        }
        if (service === "llm") {
          try {
            const saved = await persistLlmSettings({}, { refreshWizard: false });
            setSettings((prev) => ({ ...prev, ...saved }));
          } catch (error) {
            if (!silent) {
              setActionFeedback("llm", "error", `Verified, but failed to save settings: ${error.message}`);
            }
          }
        }
        await refreshWizard();
      }
    } catch (error) {
      setTestResults((prev) => ({
        ...prev,
        [service]: { state: "error", message: error.message },
      }));
      if (!silent) {
        setActionFeedback(service, "error", error.message);
      }
      setCertifications((prev) => ({
        ...prev,
        [service]: {
          ...(prev[service] || {}),
          certified: false,
          connection_status: "failed",
        },
      }));
    } finally {
      setTesting(null);
    }
  }

  async function handleNext() {
    setFooterAlert(null);
    try {
      await persistSettings({}, { refreshWizard: true });
      if (stepIndex < WIZARD_STEPS.length - 1) {
        setStepIndex((prev) => prev + 1);
      }
      setFooterAlert({ type: "success", message: "Step saved." });
      setStatus("Step saved.");
    } catch (error) {
      setFooterAlert({ type: "error", message: error.message });
      setStatus(error.message);
    }
  }

  async function handleFinishOnboarding() {
    setFooterAlert(null);
    if (!onboardingReady(verification)) {
      setFooterAlert({
        type: "error",
        message: "Certify LLM, Plex, Radarr, Sonarr, and select both library sections before finishing.",
      });
      return;
    }
    try {
      await persistSettings({ onboarding_complete: true });
      setShowWizard(false);
      const message = "Onboarding complete. Welcome to CuratorX.";
      setFooterAlert({ type: "success", message });
      setStatus(message);
      navigate("/");
    } catch (error) {
      setFooterAlert({ type: "error", message: error.message });
      setStatus(error.message);
    }
  }

  async function handleSaveSettings() {
    clearActionFeedback("save");
    try {
      await persistSettings();
      setActionFeedback("save", "success", "Settings saved.");
    } catch (error) {
      setActionFeedback("save", "error", error.message);
    }
  }

  if (!settings || !persona || !wizard) return <p>Loading settings…</p>;

  const currentStep = WIZARD_STEPS[stepIndex];

  function renderWizardStep() {
    if (currentStep === "identity_seed") {
      return (
        <section className="wizard-panel wizard-card">
          <h2>Step 1 — Identity seed</h2>
          <p className="wizard-note">Name your curator. Persona tuning adapts automatically after setup.</p>
          <label className="identity-field">
            <span>Curator name</span>
            <input
              type="text"
              data-testid="curator-name-input"
              value={persona.curator_name}
              disabled={savingPersona}
              onChange={(event) => setPersona({ ...persona, curator_name: event.target.value })}
              onBlur={(event) => savePersonaField("curator_name", event.target.value)}
            />
          </label>
          <p className="persona-preview">{preview}</p>
          <InlineAlert
            type={actionAlert?.area === "persona" ? actionAlert.type : null}
            message={actionAlert?.area === "persona" ? actionAlert.message : null}
          />
        </section>
      );
    }

    if (currentStep === "infrastructure") {
      return (
        <section className="wizard-panel wizard-card">
          <h2>Step 2 — Infrastructure verification matrix</h2>
          <p className="wizard-note">
            Verify your LLM engine, Plex server, and automation stack before mapping libraries.
          </p>

          <div className="service-cards">
            {INFRASTRUCTURE_SERVICES.map((service) => {
              const { id, label, kind } = service;
              const result = testResults[id];
              const cardClass = [
                "service-card",
                result?.state === "success" ? "service-ok" : "",
                result?.state === "error" ? "service-error" : "",
                testing === id ? "service-loading" : "",
              ]
                .filter(Boolean)
                .join(" ");

              if (kind === "llm") {
                return (
                  <div key={id} className={cardClass}>
                    <div className="service-card-header">
                      <div className="service-card-title">
                        <h3>{label}</h3>
                        <CertifiedBadge
                          certified={certifications.llm?.certified}
                          testing={testing === "llm"}
                          serviceId="llm"
                        />
                      </div>
                      <button type="button" data-testid="verify-llm" onClick={() => runTest("llm")} disabled={testing === "llm"}>
                        {testing === "llm" ? "Verifying…" : "Verify"}
                      </button>
                    </div>
                    <div className="wizard-fields">
                      <label>
                        <span>LLM provider</span>
                        <ProviderSelect
                          value={settings.llm_provider}
                          onChange={(event) => handleProviderChange(event.target.value)}
                        />
                      </label>
                      <label>
                        <span>Base URL</span>
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
                          placeholder: secretPlaceholder(
                            settings,
                            "llm_api_key",
                            "Required except for Ollama",
                          ),
                        })}
                      </label>
                      <label>
                        <span>Model</span>
                        <input
                          type="text"
                          list={settings.llm_provider === "anthropic" ? "anthropic-model-options" : undefined}
                          value={settings.llm_model ?? ""}
                          onChange={(event) => updateSettings({ llm_model: event.target.value })}
                          placeholder={LLM_MODEL_DEFAULTS[settings.llm_provider] || "gpt-4o-mini"}
                        />
                        {settings.llm_provider === "anthropic" ? (
                          <datalist id="anthropic-model-options">
                            {ANTHROPIC_MODEL_OPTIONS.map((model) => (
                              <option key={model} value={model} />
                            ))}
                          </datalist>
                        ) : null}
                      </label>
                    </div>
                    <InlineAlert
                      type={actionAlert?.area === "llm" ? actionAlert.type : result?.state}
                      message={actionAlert?.area === "llm" ? actionAlert.message : result?.message}
                    />
                  </div>
                );
              }

              const fields = service.fields || [];
              const showPlexCredentials = id === "plex" && !plexCollapsed;
              return (
                <div key={id} className={cardClass}>
                  <div className="service-card-header">
                    <div className="service-card-title">
                      <h3>{label}</h3>
                      <CertifiedBadge
                        certified={certifications[id]?.certified}
                        testing={testing === id}
                        serviceId={id}
                      />
                    </div>
                    <button type="button" data-testid={`verify-${id}`} onClick={() => runTest(id)} disabled={testing === id}>
                      {testing === id ? "Verifying…" : "Verify"}
                    </button>
                  </div>
                  {id === "plex" && plexCollapsed ? (
                    <button type="button" className="ghost" onClick={() => setPlexCollapsed(false)}>
                      Edit Plex credentials
                    </button>
                  ) : null}
                  {showPlexCredentials || id !== "plex" ? (
                    <div className="service-fields">
                      {fields.map((field) => (
                        <label key={field}>
                          <span>{field}</span>
                          {SECRET_FIELDS.includes(field) ? (
                            renderSecretInput(field, { disabled: testing === id })
                          ) : (
                            <input
                              type="text"
                              value={settings[field] ?? ""}
                              disabled={testing === id}
                              onChange={(event) => updateSettings({ [field]: event.target.value })}
                            />
                          )}
                        </label>
                      ))}
                    </div>
                  ) : null}
                  {result?.message ? (
                    <InlineAlert
                      type={actionAlert?.area === id ? actionAlert.type : result.state}
                      message={actionAlert?.area === id ? actionAlert.message : result.message}
                    />
                  ) : null}
                </div>
              );
            })}
          </div>

          {onboardingHints.length ? (
            <div className="onboarding-assistant">
              <h3>Onboarding assistant</h3>
              <div className="onboarding-hints">
                {onboardingHints.map((hint) => (
                  <p key={hint}>{hint}</p>
                ))}
              </div>
            </div>
          ) : null}
        </section>
      );
    }

    return (
      <section className="wizard-panel wizard-card">
        <h2>Step 3 — Dropdown mapping layer</h2>
        <p className="wizard-note">
          Plex is certified. Choose movie and TV libraries — credentials stay hidden unless you re-verify
          on step 2.
        </p>
        <div className="wizard-actions">
          <CertifiedBadge certified={certifications.plex?.certified} testing={testing === "plex"} serviceId="plex" />
          {!sections.length ? (
            <button type="button" className="ghost" onClick={() => runTest("plex")} disabled={testing === "plex"}>
              {testing === "plex" ? "Loading libraries…" : "Reload Plex libraries"}
            </button>
          ) : null}
        </div>
        <div className="section-dropdowns">
          <label>
            <span>Movie library</span>
            <select
              data-testid="plex-movie-section"
              value={settings.plex_movie_section ?? ""}
              onChange={(event) => handleSectionChange("plex_movie_section", event.target.value)}
              disabled={!sections.length}
            >
              <option value="">Select a movie library</option>
              {movieSections.map((section) => (
                <option key={section.key} value={section.key}>
                  {section.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>TV library</span>
            <select
              data-testid="plex-tv-section"
              value={settings.plex_tv_section ?? ""}
              onChange={(event) => handleSectionChange("plex_tv_section", event.target.value)}
              disabled={!sections.length}
            >
              <option value="">Select a TV library</option>
              {tvSections.map((section) => (
                <option key={section.key} value={section.key}>
                  {section.title}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="config-toggle" data-testid="sync-reviews-to-plex">
          <input
            type="checkbox"
            checked={Boolean(settings.sync_reviews_to_plex)}
            onChange={(event) => handleSyncReviewsToggle(event.target.checked)}
          />
          <span>Sync personal reviews to Plex star ratings</span>
        </label>
        <label className="config-toggle" data-testid="plex-collections-enabled">
          <input
            type="checkbox"
            checked={Boolean(settings?.features?.plex_collections_enabled)}
            onChange={(event) => handlePlexCollectionsToggle(event.target.checked)}
          />
          <span>Allow curator to manage Plex collections</span>
        </label>
        <InlineAlert
          type={actionAlert?.area === "plex-sections" ? actionAlert.type : null}
          message={actionAlert?.area === "plex-sections" ? actionAlert.message : null}
        />
      </section>
    );
  }

  async function handleLibrarySync() {
    setSyncingLibrary(true);
    setActionFeedback("library-sync", null);
    try {
      const job = await api("/library/sync", { method: "POST" });
      trackedSyncJobIdRef.current = job.id;
      setActiveSyncJob(job);
      syncWasRunningRef.current = job.status === "running" || job.status === "queued";
      setActionFeedback("library-sync", {
        type: "success",
        message: "Library sync started. Progress appears below.",
      });
    } catch (error) {
      setSyncingLibrary(false);
      setActionFeedback("library-sync", {
        type: "error",
        message: error.message || "Library sync failed to start.",
      });
    }
  }

  function formatLastSync(lastSync) {
    return formatLastSyncRelative(lastSync);
  }

  async function handleExportTrainingCorpus() {
    setExportingCorpus(true);
    try {
      const response = await fetch("/api/admin/export/training-corpus", { credentials: "include" });
      if (!response.ok) {
        throw new Error(`Export failed (${response.status})`);
      }
      const blob = await response.blob();
      const disposition = response.headers.get("Content-Disposition") || "";
      const match = disposition.match(/filename="([^"]+)"/);
      const filename = match?.[1] || "curatorx-training-corpus.json";
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
      setActionFeedback("training-export", {
        type: "success",
        message: "Training corpus downloaded.",
      });
    } catch (error) {
      setActionFeedback("training-export", {
        type: "error",
        message: error.message || "Training corpus export failed.",
      });
    } finally {
      setExportingCorpus(false);
    }
  }

  function renderMaintenanceDashboard() {
    return (
      <>
        <section className="config-section" data-testid="maintenance-dashboard">
          <div className="dashboard-header">
            <h2>Maintenance dashboard</h2>
            <button type="button" className="ghost" data-testid="rerun-wizard" onClick={() => setShowWizard(true)}>
              Re-run onboarding wizard
            </button>
          </div>
          <p>Re-test integrations, adjust library mapping, and tune advanced settings.</p>
        </section>

        <section className="config-section" data-testid="library-sync-card">
          <h2>Library sync</h2>
          <p>
            Pull the latest movies and shows from Plex into CuratorX. First sync can take a few minutes
            while titles are scanned and enriched.
          </p>
          <div className="config-actions">
            <button type="button" data-testid="library-sync-button" onClick={handleLibrarySync} disabled={syncingLibrary}>
              {syncingLibrary ? "Syncing…" : "Sync library"}
            </button>
          </div>
          {(() => {
            const details = formatSyncJobDetails(activeSyncJob, libraryStats);
            if (!details) return null;
            if (details.state === "running" || syncingLibrary) {
              const live = details.state === "running" ? details : formatSyncJobDetails(
                { ...(activeSyncJob || {}), status: "running", progress: activeSyncJob?.progress || { phase: "preparing", message: "Starting…" } },
                libraryStats,
              );
              return (
                <div className="library-sync-progress" data-testid="library-sync-job-status">
                  <p className="library-sync-progress-headline">
                    <strong>{live.headline}</strong>
                    {typeof live.percent === "number" ? ` · ${live.percent}%` : ""}
                  </p>
                  <p className="library-sync-progress-detail status status-secondary">
                    {live.detail}
                    {live.countHint && !String(live.detail || "").includes(String(activeSyncJob?.progress?.current ?? ""))
                      ? ` · ${live.countHint}`
                      : ""}
                  </p>
                  {typeof live.percent === "number" ? (
                    <div
                      className="library-sync-progress-bar"
                      role="progressbar"
                      aria-valuenow={live.percent}
                      aria-valuemin={0}
                      aria-valuemax={100}
                    >
                      <span className="library-sync-progress-fill" style={{ width: `${live.percent}%` }} />
                    </div>
                  ) : null}
                </div>
              );
            }
            if (details.state === "failed") {
              return (
                <p className="status status-error" data-testid="library-sync-job-status">
                  Sync failed: {details.detail}
                </p>
              );
            }
            if (details.state === "completed" && trackedSyncJobIdRef.current === activeSyncJob?.id) {
              return (
                <p className="status" data-testid="library-sync-job-status">
                  {details.headline}
                </p>
              );
            }
            return null;
          })()}
          {libraryStats ? (
            <p className="status status-secondary" data-testid="library-sync-stats">
              {libraryStats.movies} movies · {libraryStats.shows} shows
              {libraryStats.last_sync ? ` · Last synced ${formatLastSync(libraryStats.last_sync)}` : " · Never synced"}
            </p>
          ) : (
            <p className="status status-secondary" data-testid="library-sync-stats">
              No library indexed yet — run Sync library after Plex is connected.
            </p>
          )}
          <InlineAlert
            type={actionAlert?.area === "library-sync" ? actionAlert.type : null}
            message={actionAlert?.area === "library-sync" ? actionAlert.message : null}
          />
        </section>

        <section className="config-section" data-testid="library-health-dashboard">
          <h2>Library health</h2>
          <p>Quick signals for backlog, stale adds, and how much of your watched library you have rated.</p>
          {libraryHealth ? (
            <div className="library-health-grid">
              <div className="library-health-metric" data-testid="library-health-unwatched">
                <span className="library-health-value">{libraryHealth.unwatched_pct}%</span>
                <span className="library-health-label">Unwatched</span>
                <span className="library-health-detail">
                  {libraryHealth.unwatched_count} of {libraryHealth.total} titles
                </span>
              </div>
              <div className="library-health-metric" data-testid="library-health-stale">
                <span className="library-health-value">{libraryHealth.stale_adds}</span>
                <span className="library-health-label">Stale adds</span>
                <span className="library-health-detail">
                  Added {libraryHealth.stale_add_days}+ days ago, never played
                </span>
              </div>
              <div className="library-health-metric" data-testid="library-health-ratings">
                <span className="library-health-value">{libraryHealth.rating_coverage_pct}%</span>
                <span className="library-health-label">Rating coverage</span>
                <span className="library-health-detail">
                  {libraryHealth.reviewed_count} reviewed of {libraryHealth.watched_count} watched
                </span>
              </div>
            </div>
          ) : (
            <p className="status status-secondary">Run a library sync to populate health metrics.</p>
          )}
        </section>

        <section className="config-section" data-testid="training-corpus-export">
          <h2>Training corpus export</h2>
          <p>
            Download message reactions, preference facts, and personal reviews as JSON for offline taste
            training or backup.
          </p>
          <div className="config-actions">
            <button
              type="button"
              data-testid="training-corpus-export-button"
              onClick={handleExportTrainingCorpus}
              disabled={exportingCorpus}
            >
              {exportingCorpus ? "Preparing export…" : "Download training corpus"}
            </button>
          </div>
          <InlineAlert
            type={actionAlert?.area === "training-export" ? actionAlert.type : null}
            message={actionAlert?.area === "training-export" ? actionAlert.message : null}
          />
        </section>

        <PersonaSection
          persona={persona}
          setPersona={setPersona}
          savingPersona={savingPersona}
          setSavingPersona={setSavingPersona}
          actionAlert={actionAlert}
          setActionFeedback={setActionFeedback}
          showCuratorName
          onCuratorNameBlur={async (name) => {
            await putSystemConfig({ curator_name: String(name) });
            setVerification((prev) => ({
              ...prev,
              identity: Boolean(String(name || "").trim()),
            }));
          }}
        />

        <section className="config-section">
          <h2>LLM engine</h2>
          <div className="wizard-fields">
            <label>
              <span>Provider</span>
              <ProviderSelect
                value={settings.llm_provider}
                onChange={(event) => handleProviderChange(event.target.value)}
              />
            </label>
            <label>
              <span>Base URL</span>
              <input
                type="text"
                value={settings.llm_base_url ?? ""}
                onChange={(event) => updateSettings({ llm_base_url: event.target.value })}
              />
            </label>
            <label>
              <span>API key</span>
              {renderSecretInput("llm_api_key")}
            </label>
            <label>
              <span>Model</span>
              <input
                type="text"
                list={settings.llm_provider === "anthropic" ? "anthropic-model-options-maintenance" : undefined}
                value={settings.llm_model ?? ""}
                onChange={(event) => updateSettings({ llm_model: event.target.value })}
                placeholder={LLM_MODEL_DEFAULTS[settings.llm_provider] || "claude-sonnet-4-6"}
              />
              {settings.llm_provider === "anthropic" ? (
                <datalist id="anthropic-model-options-maintenance">
                  {ANTHROPIC_MODEL_OPTIONS.map((model) => (
                    <option key={model} value={model} />
                  ))}
                </datalist>
              ) : null}
            </label>
          </div>
          <button type="button" onClick={() => runTest("llm")} disabled={testing === "llm"}>
            Test LLM
          </button>
          <CertifiedBadge certified={certifications.llm?.certified} testing={testing === "llm"} serviceId="llm" />
          <InlineAlert
            type={actionAlert?.area === "llm" ? actionAlert.type : testResults.llm?.state}
            message={actionAlert?.area === "llm" ? actionAlert.message : testResults.llm?.message}
          />
        </section>

        <section className="config-section">
          <h2>Core integrations</h2>
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
                    <button type="button" onClick={() => runTest(id)} disabled={testing === id}>
                      {testing === id ? "Testing…" : "Test"}
                    </button>
                  </div>
                  <div className="service-fields">
                    {fields.map((field) => (
                      <label key={field}>
                        <span>{field}</span>
                        {SECRET_FIELDS.includes(field) ? (
                          renderSecretInput(field)
                        ) : (
                          <input
                            type="text"
                            value={settings[field] ?? ""}
                            onChange={(event) => updateSettings({ [field]: event.target.value })}
                          />
                        )}
                      </label>
                    ))}
                  </div>
                  {result?.message ? (
                    <InlineAlert
                      type={actionAlert?.area === id ? actionAlert.type : result.state}
                      message={actionAlert?.area === id ? actionAlert.message : result.message}
                    />
                  ) : null}
                </div>
              );
            })}
          </div>
        </section>

        <section className="config-section">
          <h2>Optional metadata services</h2>
          <p className="wizard-note">TMDB, Fanart.tv, and Tautulli — configure anytime after onboarding.</p>
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
                    <button type="button" onClick={() => runTest(id)} disabled={testing === id}>
                      {testing === id ? "Testing…" : "Test"}
                    </button>
                  </div>
                  <div className="service-fields">
                    {fields.map((field) => (
                      <label key={field}>
                        <span>{field}</span>
                        {SECRET_FIELDS.includes(field) ? (
                          renderSecretInput(field)
                        ) : (
                          <input
                            type="text"
                            value={settings[field] ?? ""}
                            onChange={(event) => updateSettings({ [field]: event.target.value })}
                          />
                        )}
                      </label>
                    ))}
                  </div>
                  {result?.message ? (
                    <InlineAlert
                      type={actionAlert?.area === id ? actionAlert.type : result.state}
                      message={actionAlert?.area === id ? actionAlert.message : result.message}
                    />
                  ) : null}
                </div>
              );
            })}
          </div>
        </section>

        {!showWizard ? (
          <section className="config-section" data-testid="multi-user-settings">
            <h2>Multi-user auth (optional)</h2>
            <p className="wizard-note">
              Require Plex sign-in for household members. The first Plex account to sign in becomes owner; later accounts start as members.
            </p>
            <label className="config-toggle" data-testid="multi-user-enabled-toggle">
              <input
                type="checkbox"
                checked={Boolean(settings?.features?.multi_user_enabled)}
                onChange={(event) => {
                  const enabled = event.target.checked;
                  const nextAuthMode = enabled ? "plex" : "disabled";
                  updateFeatureFlags({ multi_user_enabled: enabled });
                  updateAuthSettings({ mode: nextAuthMode, plex_login_enabled: true });
                  persistSettings({
                    features: { ...(settings.features || {}), multi_user_enabled: enabled },
                    auth: {
                      ...(settings.auth || {}),
                      mode: nextAuthMode,
                      plex_login_enabled: true,
                    },
                  })
                    .then(() =>
                      setActionFeedback(
                        "multi-user",
                        "success",
                        enabled
                          ? "Multi-user auth enabled. Sign in with Plex on the login page."
                          : "Multi-user auth disabled.",
                      ),
                    )
                    .catch((error) => setActionFeedback("multi-user", "error", error.message));
                }}
              />
              <span>Enable multi-user auth</span>
            </label>
            {settings?.features?.multi_user_enabled ? (
              <>
                <div className="service-fields">
                  <label>
                    <span>Auth mode</span>
                    <select
                      data-testid="auth-mode-select"
                      value={settings?.auth?.mode || "plex"}
                      onChange={(event) => {
                        const mode = event.target.value;
                        updateAuthSettings({ mode });
                        persistSettings({
                          auth: { ...(settings.auth || {}), mode },
                        }).catch((error) => setActionFeedback("multi-user", "error", error.message));
                      }}
                    >
                      <option value="plex">Plex token login</option>
                      <option value="disabled">Disabled</option>
                      <option value="oidc" disabled>
                        OIDC (coming soon)
                      </option>
                      <option value="local" disabled>
                        Local accounts (coming soon)
                      </option>
                    </select>
                  </label>
                  <label className="config-toggle" data-testid="plex-login-enabled-toggle">
                    <input
                      type="checkbox"
                      checked={settings?.auth?.plex_login_enabled !== false}
                      onChange={(event) => {
                        const enabled = event.target.checked;
                        updateAuthSettings({ plex_login_enabled: enabled });
                        persistSettings({
                          auth: { ...(settings.auth || {}), plex_login_enabled: enabled },
                        }).catch((error) => setActionFeedback("multi-user", "error", error.message));
                      }}
                    />
                    <span>Allow Plex sign-in</span>
                  </label>
                </div>
                {featureFlags?.user?.role === "owner" || !featureFlags?.features?.multi_user_enabled ? (
                  <div className="user-management" data-testid="user-management">
                    <h3>Users</h3>
                    {usersLoading ? <p className="wizard-note">Loading users…</p> : null}
                    {!usersLoading && managedUsers.length === 0 ? (
                      <p className="wizard-note">No Plex users have signed in yet.</p>
                    ) : null}
                    {managedUsers.length ? (
                      <ul className="user-management-list">
                        {managedUsers.map((entry) => (
                          <li key={entry.id} className="user-management-row" data-testid={`user-row-${entry.id}`}>
                            <div>
                              <strong>{entry.display_name}</strong>
                              <span>{entry.email || entry.plex_user_id || entry.id}</span>
                              {entry.seerr_user_id ? (
                                <span className="user-management-meta">Seerr #{entry.seerr_user_id}</span>
                              ) : (
                                <span className="user-management-meta">Seerr not linked</span>
                              )}
                            </div>
                            <select
                              value={entry.role}
                              disabled={entry.id === featureFlags?.user?.id && entry.role === "owner"}
                              onChange={(event) => handleUserRoleChange(entry.id, event.target.value)}
                            >
                              <option value="owner">Owner</option>
                              <option value="member">Member</option>
                              <option value="guest">Guest</option>
                            </select>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                    {actionAlert?.area === "users" || actionAlert?.area === "multi-user" ? (
                      <InlineAlert
                        type={actionAlert.type}
                        message={actionAlert.message}
                        testId="multi-user-alert"
                      />
                    ) : null}
                  </div>
                ) : (
                  <p className="wizard-note">Sign in as owner to manage household users.</p>
                )}
              </>
            ) : null}
          </section>
        ) : null}

        {!showWizard ? (
          <section className="config-section" data-testid="seerr-settings">
            <h2>Seerr (optional)</h2>
            <p className="wizard-note">
              Household discovery and requests via Seerr/Overseerr. Members see &quot;Request in Seerr&quot; instead of Radarr/Sonarr adds.
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
                      setActionFeedback(
                        "seerr",
                        "success",
                        enabled ? "Seerr integration enabled." : "Seerr integration disabled.",
                      ),
                    )
                    .catch((error) => setActionFeedback("seerr", "error", error.message));
                }}
              />
              <span>Enable Seerr integration</span>
            </label>
            <div className={`service-card ${testResults.seerr?.state === "success" ? "service-ok" : ""} ${testing === "seerr" ? "service-loading" : ""} ${testResults.seerr?.state === "error" ? "service-error" : ""}`}>
                <div className="service-card-header">
                  <div className="service-card-title">
                    <h3>Seerr connection</h3>
                    <CertifiedBadge
                      certified={certifications.seerr?.certified}
                      testing={testing === "seerr"}
                      serviceId="seerr"
                    />
                  </div>
                  <button type="button" data-testid="verify-seerr" onClick={() => runTest("seerr")} disabled={testing === "seerr"}>
                    {testing === "seerr" ? "Testing…" : "Test connection"}
                  </button>
                </div>
                <div className="service-fields">
                  <label>
                    <span>Seerr URL</span>
                    <input
                      type="text"
                      data-testid="seerr-url"
                      value={settings?.seerr?.url ?? ""}
                      onChange={(event) => updateSeerrSettings({ url: event.target.value })}
                      onBlur={() =>
                        persistSettings({
                          seerr: { ...(settings.seerr || {}), url: settings?.seerr?.url ?? "" },
                        }).catch((error) => setActionFeedback("seerr", "error", error.message))
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
                      }).catch((error) => setActionFeedback("seerr", "error", error.message));
                    }}
                  />
                  <span>Link Plex users to Seerr on login</span>
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
                      }).catch((error) => setActionFeedback("seerr", "error", error.message));
                    }}
                  />
                  <span>Require linked Seerr user before requests</span>
                </label>
                {testResults.seerr?.message ? (
                  <InlineAlert
                    type={actionAlert?.area === "seerr" ? actionAlert.type : testResults.seerr.state}
                    message={actionAlert?.area === "seerr" ? actionAlert.message : testResults.seerr.message}
                  />
                ) : null}
              </div>
          </section>
        ) : null}

        <section className="config-section" data-testid="plex-library-mapping">
          <h2>Plex library mapping</h2>
          <p className="wizard-note">Update movie and TV libraries when your Plex layout changes.</p>
          <div className="wizard-actions">
            <CertifiedBadge certified={certifications.plex?.certified} testing={testing === "plex"} serviceId="plex" />
            {!sections.length ? (
              <button type="button" className="ghost" onClick={() => runTest("plex")} disabled={testing === "plex"}>
                {testing === "plex" ? "Loading libraries…" : "Reload Plex libraries"}
              </button>
            ) : null}
          </div>
          <div className="section-dropdowns">
            <label>
              <span>Movie library</span>
              <select
                data-testid="plex-movie-section"
                value={settings.plex_movie_section ?? ""}
                onChange={(event) => handleSectionChange("plex_movie_section", event.target.value)}
                disabled={!sections.length}
              >
                <option value="">Select a movie library</option>
                {movieSections.map((section) => (
                  <option key={section.key} value={section.key}>
                    {section.title}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>TV library</span>
              <select
                data-testid="plex-tv-section"
                value={settings.plex_tv_section ?? ""}
                onChange={(event) => handleSectionChange("plex_tv_section", event.target.value)}
                disabled={!sections.length}
              >
                <option value="">Select a TV library</option>
                {tvSections.map((section) => (
                  <option key={section.key} value={section.key}>
                    {section.title}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="config-toggle" data-testid="sync-reviews-to-plex">
            <input
              type="checkbox"
              checked={Boolean(settings.sync_reviews_to_plex)}
              onChange={(event) => handleSyncReviewsToggle(event.target.checked)}
            />
            <span>Sync personal reviews to Plex star ratings</span>
          </label>
          <p className="wizard-note">
            When enabled, saving a 1–5 star review in CuratorX writes the matching Plex rating (2, 4, 6, 8, or 10).
          </p>
          <label className="config-toggle" data-testid="plex-collections-enabled">
            <input
              type="checkbox"
              checked={Boolean(settings?.features?.plex_collections_enabled)}
              onChange={(event) => handlePlexCollectionsToggle(event.target.checked)}
            />
            <span>Allow curator to manage Plex collections</span>
          </label>
          <p className="wizard-note">
            When enabled, the curator can propose creating Plex collections or adding owned titles to existing ones (confirmation required).
          </p>
          <InlineAlert
            type={actionAlert?.area === "plex-sections" ? actionAlert.type : null}
            message={actionAlert?.area === "plex-sections" ? actionAlert.message : null}
          />
        </section>

        <section className="config-section config-section-collapsible">
          <button
            type="button"
            className="collapsible-header"
            data-testid="advanced-toggle"
            aria-expanded={advancedOpen}
            onClick={() => setAdvancedOpen((open) => !open)}
          >
            <h2>Advanced settings</h2>
            <span className="collapsible-chevron">{advancedOpen ? "▾" : "▸"}</span>
          </button>
          {advancedOpen ? (
            <div className="collapsible-body">
              <div className="config-section-sub">
                <h3>Paths and sync</h3>
                <div className="config-grid">
                  {[
                    "movies_root",
                    "tv_root",
                    "radarr_root_folder",
                    "sonarr_root_folder",
                    "library_sync_interval_hours",
                    "tv_page_size",
                    "library_enrich_workers",
                  ].map((key) => (
                    <label key={key}>
                      <span>{key}</span>
                      <input
                        type="text"
                        value={settings[key] ?? ""}
                        onChange={(event) =>
                          updateSettings({
                            [key]:
                              key.endsWith("_hours") ||
                              key === "tv_page_size" ||
                              key === "library_enrich_workers"
                                ? Number(event.target.value || 0)
                                : event.target.value,
                          })
                        }
                      />
                    </label>
                  ))}
                  <label>
                    <span>library_sync_hour</span>
                    <select
                      data-testid="library-sync-hour"
                      value={
                        settings.library_sync_hour === null ||
                        settings.library_sync_hour === undefined
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
                      <option value="">Any / interval only</option>
                      {Array.from({ length: 24 }, (_, hour) => (
                        <option key={hour} value={hour}>
                          {String(hour).padStart(2, "0")}:00 (local)
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <p className="slider-help-text" style={{ marginTop: "0.5rem" }}>
                  Preferred sync hour uses the container local timezone. On Unraid, set the{" "}
                  <code>TZ</code> env (e.g. <code>America/New_York</code>) if the clock is wrong.
                </p>
                <div className="config-actions">
                  <button type="button" onClick={handleSaveSettings}>
                    Save settings
                  </button>
                </div>
                <InlineAlert type={actionAlert?.area === "save" ? actionAlert.type : null} message={actionAlert?.area === "save" ? actionAlert.message : null} />
              </div>
            </div>
          ) : null}
        </section>
      </>
    );
  }

  return (
    <div className="config-page">
      <header className="topbar">
        <div>
          <p className="eyebrow">Configuration</p>
          <h1>{showWizard ? "Onboarding wizard" : "Curator maintenance"}</h1>
        </div>
        <Link to="/" className="btn-link">
          Back to chat
        </Link>
      </header>

      {showWizard ? (
        <>
          <nav className="wizard-nav" aria-label="Onboarding steps" data-testid="wizard-nav">
            {WIZARD_STEPS.map((step, index) => {
              const unlocked = stepUnlocked(index, verification);
              const active = index === stepIndex;
              const complete =
                (wizard.steps[step]?.complete ?? false) ||
                (index === 0 && verification.identity) ||
                (index === 1 &&
                  verification.llm &&
                  verification.plex &&
                  verification.radarr &&
                  verification.sonarr) ||
                (index === 2 && verification.sections);
              return (
                <button
                  key={step}
                  type="button"
                  data-testid={`wizard-step-${step}`}
                  className={[
                    "wizard-step",
                    active ? "wizard-step-active" : "",
                    complete ? "wizard-step-complete" : "",
                    !unlocked ? "wizard-step-locked" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  disabled={!unlocked}
                  onClick={() => unlocked && setStepIndex(index)}
                >
                  <span className="wizard-step-num">{index + 1}</span>
                  {STEP_LABELS[step]}
                </button>
              );
            })}
          </nav>

          {renderWizardStep()}

          <div className="wizard-footer">
            {stepIndex > 0 ? (
              <button type="button" className="ghost" data-testid="wizard-back" onClick={() => setStepIndex((prev) => prev - 1)}>
                Back
              </button>
            ) : (
              <span />
            )}
            <div className="wizard-footer-actions">
              {stepIndex < WIZARD_STEPS.length - 1 ? (
                <button type="button" data-testid="wizard-next" onClick={handleNext} disabled={!canAdvance(stepIndex, verification)}>
                  Next
                </button>
              ) : (
                <button type="button" data-testid="wizard-finish" onClick={handleFinishOnboarding} disabled={!onboardingReady(verification)}>
                  Finish onboarding
                </button>
              )}
              <InlineAlert type={footerAlert?.type} message={footerAlert?.message} testId="wizard-footer-alert" />
            </div>
          </div>
        </>
      ) : (
        renderMaintenanceDashboard()
      )}

      {status ? <p className="status status-secondary">{status}</p> : null}
    </div>
  );
}

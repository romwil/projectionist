import { useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, useNavigate, useOutletContext, useParams } from "react-router-dom";
import {
  AUTO_CERTIFY_SERVICES,
  ANTHROPIC_MODEL_OPTIONS,
  LLM_MODEL_DEFAULTS,
  LLM_PROVIDER_DEFAULTS,
  LLM_PROVIDER_OPTIONS,
  WIZARD_STEPS,
  api,
  clearMcpKey,
  getAuthMe,
  getFeatures,
  getHealth,
  getPersona,
  getSettings,
  getWizardStatus,
  getPlexSections,
  listJobs,
  deleteUser,
  listUsers,
  patchUserDisabled,
  putPersona,
  putSystemConfig,
  resolveModelForProvider,
  rotateMcpKey,
  saveSettings,
  syncUserSeerr,
  testService,
  updateUserRole,
} from "../api/client";
import AdvancedSettings from "../components/AdvancedSettings";
import PersonaSection from "../components/PersonaSection";
import {
  formatLastSyncRelative,
  formatSyncJobDetails,
} from "../lib/jobProgress.js";

const ADMIN_SECTIONS = new Set([
  "overview",
  "connections",
  "libraries",
  "sync",
  "persona",
  "household",
  "seerr",
  "advanced",
]);

const SECTION_TITLES = {
  overview: "Overview",
  connections: "Connections",
  libraries: "Libraries",
  sync: "Library sync",
  persona: "Persona",
  household: "Household",
  seerr: "Seerr",
  advanced: "Advanced",
};

const SECRET_FIELDS = [
  "plex_token",
  "radarr_api_key",
  "sonarr_api_key",
  "tmdb_api_key",
  "tvdb_api_key",
  "fanart_api_key",
  "omdb_api_key",
  "tautulli_api_key",
  "llm_api_key",
  "seerr_api_key",
];

/** User-facing labels for settings keys (never show raw snake_case in the UI). */
const FIELD_LABELS = {
  plex_url: "Plex server URL",
  plex_token: "Plex server token",
  radarr_url: "Radarr URL",
  radarr_api_key: "API key",
  sonarr_url: "Sonarr URL",
  sonarr_api_key: "API key",
  tmdb_api_key: "API key",
  tvdb_api_key: "TVDB API key",
  fanart_api_key: "API key",
  omdb_api_key: "OMDb API key",
  long_synopsis_source: "Long synopsis source",
  tautulli_url: "Tautulli URL",
  tautulli_api_key: "API key",
  movies_root: "Movies folder path",
  tv_root: "TV folder path",
  radarr_root_folder: "Radarr root folder",
  sonarr_root_folder: "Sonarr root folder",
  library_sync_interval_hours: "Auto-sync every (hours)",
  tv_page_size: "TV titles per sync page",
  library_enrich_workers: "Parallel enrich workers",
  library_sync_hour: "Preferred sync hour",
};

const FIELD_PLACEHOLDERS = {
  plex_url: "http://192.168.1.50:32400",
  plex_token: "Server token for library access",
  radarr_url: "http://192.168.1.50:7878",
  sonarr_url: "http://192.168.1.50:8989",
  tautulli_url: "http://192.168.1.50:8181",
};

const FIELD_HELP = {
  plex_token:
    "Lets CuratorX read your Plex libraries (sync, collections, ratings). This is a server token for the Media Server — not the same as household Sign in with Plex on the login page.",
  tmdb_api_key: "Powers posters, details, and discovery for titles not yet in your library.",
  tvdb_api_key: "Optional TV metadata research. A TVDB v4 API key/subscription is required.",
  fanart_api_key: "Optional richer backdrop art. Leave blank if you only need TMDB.",
  omdb_api_key:
    "Optional. Adds IMDb-aligned plot research when configured; also supports long synopsis enrichment.",
  long_synopsis_source:
    "Defaults to wikipedia (free, no key, deeper plot without LLM). Set to off to disable, or omdb / auto.",
  tautulli_url: "Optional: watch history for purge suggestions and “what we’ve been watching”.",
  movies_root: "Host path Radarr uses for movies (advanced; usually matches Radarr).",
  tv_root: "Host path Sonarr uses for TV (advanced; usually matches Sonarr).",
  library_enrich_workers: "How many titles to enrich at once during sync. Lower if Unraid feels busy.",
};

function fieldLabel(field) {
  return FIELD_LABELS[field] || field.replace(/_/g, " ");
}

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
        Connected ✓
      </span>
    );
  }
  return (
    <span className="certified-badge certified-badge-pending" data-testid={`certified-badge-${serviceId}`}>
      Not connected
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
  identity_seed: "Name",
  infrastructure: "Connections",
  dropdown_mapping: "Libraries",
};

const INFRASTRUCTURE_SERVICES = [
  { id: "llm", label: "Language model", kind: "llm" },
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
  const { section: sectionParam } = useParams();
  const outletContext = useOutletContext() || {};
  const setWizardMode = outletContext.setWizardMode;
  const section = ADMIN_SECTIONS.has(sectionParam) ? sectionParam : "overview";
  const showSection = (id) => section === id;
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
  const [visibleSecrets, setVisibleSecrets] = useState({});
  const [libraryStats, setLibraryStats] = useState(null);
  const [libraryHealth, setLibraryHealth] = useState(null);
  const [exportingCorpus, setExportingCorpus] = useState(false);
  const [syncingLibrary, setSyncingLibrary] = useState(false);
  const [activeSyncJob, setActiveSyncJob] = useState(null);
  const [featureFlags, setFeatureFlags] = useState(null);
  const [appVersion, setAppVersion] = useState("");
  const [managedUsers, setManagedUsers] = useState([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [mcpRevealedKeys, setMcpRevealedKeys] = useState({});
  const [mcpKeyBusy, setMcpKeyBusy] = useState(null);
  const trackedSyncJobIdRef = useRef(null);
  const syncWasRunningRef = useRef(false);

  useEffect(() => {
    if (typeof setWizardMode === "function") {
      setWizardMode(showWizard);
    }
    return () => {
      if (typeof setWizardMode === "function") {
        setWizardMode(false);
      }
    };
  }, [setWizardMode, showWizard]);

  const preview = useMemo(() => wizardPersonaPreview(persona), [persona]);
  const movieSections = useMemo(() => sections.filter((s) => s.type === "movie"), [sections]);
  const tvSections = useMemo(() => sections.filter((s) => s.type === "show"), [sections]);

  function applyCertifications(certMap) {
    setCertifications(certMap || {});
    const initialResults = {};
    for (const [service, cert] of Object.entries(certMap || {})) {
      if (cert?.certified) {
        initialResults[service] = { state: "success", message: "Connected" };
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
    ).catch(console.error);
    getFeatures()
      .then((data) => setFeatureFlags(data))
      .catch(() => setFeatureFlags(null));
    getHealth()
      .then((data) => setAppVersion(data?.version || ""))
      .catch(() => setAppVersion(""));
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

  async function handleUserDisableToggle(entry) {
    const nextDisabled = !entry.disabled;
    const label = entry.display_name || entry.email || entry.id;
    if (
      nextDisabled &&
      !window.confirm(`Disable ${label}? They will not be able to sign in until re-enabled.`)
    ) {
      return;
    }
    try {
      await patchUserDisabled(entry.id, nextDisabled);
      await refreshManagedUsers();
      setActionFeedback(
        "users",
        "success",
        nextDisabled ? "User disabled." : "User re-enabled.",
      );
    } catch (error) {
      setActionFeedback("users", "error", error.message);
    }
  }

  async function handleUserRemove(entry) {
    const label = entry.display_name || entry.email || entry.id;
    if (!window.confirm(`Remove ${label} from this household? This cannot be undone.`)) {
      return;
    }
    try {
      await deleteUser(entry.id);
      await refreshManagedUsers();
      setActionFeedback("users", "success", "User removed.");
    } catch (error) {
      setActionFeedback("users", "error", error.message);
    }
  }

  async function handleUserSyncSeerr(entry) {
    const authToken = window.prompt(
      `Paste a Plex auth token for ${entry.display_name || "this user"} to sync their Seerr account.`,
    );
    if (!authToken || !String(authToken).trim()) return;
    try {
      await syncUserSeerr(entry.id, String(authToken).trim());
      await refreshManagedUsers();
      setActionFeedback("users", "success", "Seerr account linked.");
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
        message: "Connect your language model, Plex, Radarr, and Sonarr, and choose movie and TV libraries before finishing.",
      });
      return;
    }
    try {
      await persistSettings({ onboarding_complete: true });
      setShowWizard(false);
      const message = "Setup complete. Welcome to CuratorX.";
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

  async function handleRotateMcpKey(which) {
    const label = which === "privacy" ? "privacy" : "full";
    if (
      !window.confirm(
        `Regenerate the ${label} MCP API key? Clients using the old key will stop working until you update them.`,
      )
    ) {
      return;
    }
    clearActionFeedback("mcp");
    setMcpKeyBusy(`rotate-${which}`);
    try {
      const result = await rotateMcpKey(which);
      if (result.settings) {
        setSettings((prev) => ({ ...prev, ...result.settings }));
      }
      setMcpRevealedKeys((prev) => ({ ...prev, [which]: result.key }));
      setActionFeedback(
        "mcp",
        "success",
        `${label.charAt(0).toUpperCase() + label.slice(1)} MCP key regenerated. Copy it now — it won’t be shown again.`,
      );
    } catch (error) {
      setActionFeedback("mcp", "error", error.message);
    } finally {
      setMcpKeyBusy(null);
    }
  }

  async function handleClearMcpKey(which) {
    const label = which === "privacy" ? "privacy" : "full";
    if (!window.confirm(`Clear the ${label} MCP API key from settings?`)) {
      return;
    }
    clearActionFeedback("mcp");
    setMcpKeyBusy(`clear-${which}`);
    try {
      const result = await clearMcpKey(which);
      if (result.settings) {
        setSettings((prev) => ({ ...prev, ...result.settings }));
      }
      setMcpRevealedKeys((prev) => {
        const next = { ...prev };
        delete next[which];
        return next;
      });
      setActionFeedback("mcp", "success", `${label.charAt(0).toUpperCase() + label.slice(1)} MCP key cleared.`);
    } catch (error) {
      setActionFeedback("mcp", "error", error.message);
    } finally {
      setMcpKeyBusy(null);
    }
  }

  async function copyMcpKey(which) {
    const value = mcpRevealedKeys[which];
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setActionFeedback("mcp", "success", "MCP key copied to clipboard.");
    } catch {
      setActionFeedback("mcp", "error", "Could not copy — select the key and copy manually.");
    }
  }

  if (sectionParam && !ADMIN_SECTIONS.has(sectionParam)) {
    return <Navigate to="/admin/overview" replace />;
  }

  if (!settings || !persona || !wizard) {
    return (
      <div className="config-page admin-config-page" data-testid="config-loading">
        <p className="status status-secondary">Loading configuration…</p>
      </div>
    );
  }

  const currentStep = WIZARD_STEPS[stepIndex];

  function renderWizardStep() {
    if (currentStep === "identity_seed") {
      return (
        <section className="wizard-panel wizard-card">
          <h2>Step 1 — Name your curator</h2>
          <p className="wizard-note">
            Pick a name for the voice in chat. You can refine personality later under Settings.
          </p>
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
          <h2>Step 2 — Connect your stack</h2>
          <p className="wizard-note">
            Point CuratorX at your language model, Plex server, Radarr, and Sonarr. Hit Verify on each
            card so we know they respond before you pick libraries.
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
                        <span className="wizard-note field-help">
                          Where your model lives (OpenAI, Anthropic, Ollama, or another OpenAI-compatible endpoint).
                        </span>
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
                        <span>Model name</span>
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
                          <span>{fieldLabel(field)}</span>
                          {SECRET_FIELDS.includes(field) ? (
                            renderSecretInput(field, {
                              disabled: testing === id,
                              placeholder: FIELD_PLACEHOLDERS[field],
                            })
                          ) : (
                            <input
                              type="text"
                              value={settings[field] ?? ""}
                              disabled={testing === id}
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
              <h3>Setup tips</h3>
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
        <h2>Step 3 — Choose your libraries</h2>
        <p className="wizard-note">
          Plex is connected. Select which movie and TV libraries CuratorX should index. You can change
          these later under Settings.
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
          <span>Copy star ratings to Plex when you review a title</span>
        </label>
        <label className="config-toggle" data-testid="plex-collections-enabled">
          <input
            type="checkbox"
            checked={Boolean(settings?.features?.plex_collections_enabled)}
            onChange={(event) => handlePlexCollectionsToggle(event.target.checked)}
          />
          <span>Let the curator propose Plex collections</span>
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
        message: "Taste data downloaded.",
      });
    } catch (error) {
      setActionFeedback("training-export", {
        type: "error",
        message: error.message || "Taste data export failed.",
      });
    } finally {
      setExportingCorpus(false);
    }
  }

  function renderMaintenanceDashboard() {
    return (
      <>
        {showSection("overview") ? (
        <section className="config-section" data-testid="maintenance-dashboard">
          <div className="dashboard-header">
            <h2>Connection overview</h2>
            <button type="button" className="ghost" data-testid="rerun-wizard" onClick={() => setShowWizard(true)}>
              Re-run setup
            </button>
          </div>
          <p>Test connections, pick libraries, and adjust optional household features.</p>
        </section>
        ) : null}

        {showSection("sync") ? (
        <section className="config-section" data-testid="library-sync-card">
          <h2>Library sync</h2>
          <p>
            Refresh CuratorX from your Plex libraries. The first sync can take a few minutes while titles
            are indexed and enriched.
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
        ) : null}

        {showSection("overview") ? (
        <section className="config-section" data-testid="library-health-dashboard">
          <h2>Library health</h2>
          <p>A quick read on backlog and how much of what you watch you have rated.</p>
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
                <span className="library-health-label">Never played</span>
                <span className="library-health-detail">
                  Added {libraryHealth.stale_add_days}+ days ago, not started
                </span>
              </div>
              <div className="library-health-metric" data-testid="library-health-ratings">
                <span className="library-health-value">{libraryHealth.rating_coverage_pct}%</span>
                <span className="library-health-label">Rated of watched</span>
                <span className="library-health-detail">
                  {libraryHealth.reviewed_count} reviewed of {libraryHealth.watched_count} watched
                </span>
              </div>
            </div>
          ) : (
            <p className="status status-secondary">Run Library sync to fill in these stats.</p>
          )}
        </section>
        ) : null}

        {showSection("overview") ? (
        <section className="config-section" data-testid="training-corpus-export">
          <h2>Export taste data</h2>
          <p>
            Download your chat reactions, saved preferences, and personal reviews as JSON — useful for
            backup or offline experiments.
          </p>
          <div className="config-actions">
            <button
              type="button"
              data-testid="training-corpus-export-button"
              onClick={handleExportTrainingCorpus}
              disabled={exportingCorpus}
            >
              {exportingCorpus ? "Preparing export…" : "Download taste data"}
            </button>
          </div>
          <InlineAlert
            type={actionAlert?.area === "training-export" ? actionAlert.type : null}
            message={actionAlert?.area === "training-export" ? actionAlert.message : null}
          />
        </section>
        ) : null}

        {showSection("persona") ? (
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
        ) : null}

        {showSection("connections") ? (
        <>
        <section className="config-section">
          <h2>Language model</h2>
          <p className="wizard-note">The AI that powers chat recommendations. Bring your own key or run Ollama locally.</p>
          <div className="wizard-fields">
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
            Test connection
          </button>
          <CertifiedBadge certified={certifications.llm?.certified} testing={testing === "llm"} serviceId="llm" />
          <InlineAlert
            type={actionAlert?.area === "llm" ? actionAlert.type : testResults.llm?.state}
            message={actionAlert?.area === "llm" ? actionAlert.message : testResults.llm?.message}
          />
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
                    <button type="button" onClick={() => runTest(id)} disabled={testing === id}>
                      {testing === id ? "Testing…" : "Test"}
                    </button>
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
                    <button type="button" onClick={() => runTest(id)} disabled={testing === id}>
                      {testing === id ? "Testing…" : "Test"}
                    </button>
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
        ) : null}

        {!showWizard && showSection("household") ? (
          <section className="config-section" data-testid="multi-user-settings">
            <h2>Household login (optional)</h2>
            <p className="wizard-note">
              When enabled, people open CuratorX via <strong>Sign in with Plex</strong> (plex.tv PIN / link
              on the login page). The first account becomes owner; later accounts start as members. This is
              separate from the Plex <em>server</em> token above used for library sync.
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
                          ? "Household login enabled. Members use Sign in with Plex (PIN) on the login page."
                          : "Household login disabled.",
                      ),
                    )
                    .catch((error) => setActionFeedback("multi-user", "error", error.message));
                }}
              />
              <span>Require Plex sign-in for the app</span>
            </label>
            {settings?.features?.multi_user_enabled ? (
              <>
                <div className="service-fields">
                  <label>
                    <span>Sign-in method</span>
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
                      <option value="plex">Plex (recommended)</option>
                      <option value="disabled">Off</option>
                      <option value="oidc" disabled>
                        Other providers (coming soon)
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
                    <span>Allow Sign in with Plex (PIN)</span>
                  </label>
                  <p className="wizard-note field-help">
                    Primary path is the PIN / link button on the login page. Token paste there is an advanced
                    fallback only — do not look for a token on plex.tv account settings.
                  </p>
                </div>
                {featureFlags?.user?.role === "owner" || !featureFlags?.features?.multi_user_enabled ? (
                  <div className="user-management" data-testid="user-management">
                    <h3>Household users</h3>
                    {usersLoading ? <p className="wizard-note">Loading users…</p> : null}
                    {!usersLoading && managedUsers.length === 0 ? (
                      <p className="wizard-note" data-testid="users-empty-state">
                        Household members appear after Sign in with Plex
                      </p>
                    ) : null}
                    {managedUsers.length ? (
                      <div className="user-management-table-wrap">
                        <table className="user-management-table" data-testid="users-table">
                          <thead>
                            <tr>
                              <th scope="col">Name</th>
                              <th scope="col">Email</th>
                              <th scope="col">Role</th>
                              <th scope="col">Seerr</th>
                              <th scope="col">Status</th>
                              <th scope="col">Actions</th>
                            </tr>
                          </thead>
                          <tbody>
                            {managedUsers.map((entry) => {
                              const isSelf = entry.id === featureFlags?.user?.id;
                              const seerrLinked = Boolean(entry.seerr_linked ?? entry.seerr_user_id);
                              return (
                                <tr
                                  key={entry.id}
                                  className={entry.disabled ? "user-row-disabled" : undefined}
                                  data-testid={`user-row-${entry.id}`}
                                >
                                  <td>
                                    <strong>{entry.display_name || "—"}</strong>
                                  </td>
                                  <td>{entry.email || "—"}</td>
                                  <td>
                                    <select
                                      aria-label={`Role for ${entry.display_name || entry.id}`}
                                      value={entry.role}
                                      disabled={isSelf && entry.role === "owner"}
                                      onChange={(event) =>
                                        handleUserRoleChange(entry.id, event.target.value)
                                      }
                                    >
                                      <option value="owner">Owner</option>
                                      <option value="member">Member</option>
                                      <option value="guest">Guest</option>
                                    </select>
                                  </td>
                                  <td>
                                    {seerrLinked ? (
                                      <span className="user-status-pill linked">
                                        Linked{entry.seerr_user_id ? ` #${entry.seerr_user_id}` : ""}
                                      </span>
                                    ) : (
                                      <span className="user-status-pill">Not linked</span>
                                    )}
                                  </td>
                                  <td>
                                    <span
                                      className={`user-status-pill ${entry.disabled ? "disabled" : "active"}`}
                                    >
                                      {entry.disabled ? "Disabled" : "Active"}
                                    </span>
                                  </td>
                                  <td>
                                    <div className="user-management-actions">
                                      <button
                                        type="button"
                                        className="ghost"
                                        data-testid={`user-disable-${entry.id}`}
                                        disabled={isSelf}
                                        onClick={() => handleUserDisableToggle(entry)}
                                      >
                                        {entry.disabled ? "Enable" : "Disable"}
                                      </button>
                                      <button
                                        type="button"
                                        className="ghost"
                                        data-testid={`user-sync-seerr-${entry.id}`}
                                        onClick={() => handleUserSyncSeerr(entry)}
                                      >
                                        Sync Seerr
                                      </button>
                                      <button
                                        type="button"
                                        className="ghost danger"
                                        data-testid={`user-remove-${entry.id}`}
                                        disabled={isSelf}
                                        onClick={() => handleUserRemove(entry)}
                                      >
                                        Remove
                                      </button>
                                    </div>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
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

        {!showWizard && showSection("seerr") ? (
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
                      setActionFeedback(
                        "seerr",
                        "success",
                        enabled ? "Seerr requests enabled." : "Seerr requests disabled.",
                      ),
                    )
                    .catch((error) => setActionFeedback("seerr", "error", error.message));
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
                  <button type="button" data-testid="verify-seerr" onClick={() => runTest("seerr")} disabled={testing === "seerr"}>
                    {testing === "seerr" ? "Testing…" : "Test connection"}
                  </button>
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
                      }).catch((error) => setActionFeedback("seerr", "error", error.message));
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
        ) : null}

        {showSection("libraries") ? (
        <section className="config-section" data-testid="plex-library-mapping">
          <h2>Plex libraries</h2>
          <p className="wizard-note">Choose which movie and TV libraries CuratorX indexes. Update these if you rename or add libraries in Plex.</p>
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
            <span>Copy star ratings to Plex when you review a title</span>
          </label>
          <p className="wizard-note">
            A 1–5 star review in CuratorX becomes the matching Plex rating (2, 4, 6, 8, or 10).
          </p>
          <label className="config-toggle" data-testid="plex-collections-enabled">
            <input
              type="checkbox"
              checked={Boolean(settings?.features?.plex_collections_enabled)}
              onChange={(event) => handlePlexCollectionsToggle(event.target.checked)}
            />
            <span>Let the curator propose Plex collections</span>
          </label>
          <p className="wizard-note">
            The curator can suggest creating a collection or adding titles you already own — you always confirm first.
          </p>
          <InlineAlert
            type={actionAlert?.area === "plex-sections" ? actionAlert.type : null}
            message={actionAlert?.area === "plex-sections" ? actionAlert.message : null}
          />
        </section>
        ) : null}

        {showSection("advanced") ? (
          <AdvancedSettings
            settings={settings}
            updateSettings={updateSettings}
            onSavePathsAndSync={handleSaveSettings}
            onRotateMcpKey={handleRotateMcpKey}
            onClearMcpKey={handleClearMcpKey}
            onCopyMcpKey={copyMcpKey}
            mcpRevealedKeys={mcpRevealedKeys}
            mcpKeyBusy={mcpKeyBusy}
            saveAlert={
              actionAlert?.area === "save"
                ? { type: actionAlert.type, message: actionAlert.message }
                : null
            }
            mcpAlert={
              actionAlert?.area === "mcp"
                ? { type: actionAlert.type, message: actionAlert.message }
                : null
            }
          />
        ) : null}

        {appVersion && showSection("overview") ? (
          <p className="status status-secondary" data-testid="app-version">
            CuratorX {appVersion}
          </p>
        ) : null}
      </>
    );
  }

  return (
    <div className={`config-page admin-config-page ${showWizard ? "config-wizard-mode" : ""}`}>
      <header className="topbar admin-section-topbar">
        <div>
          <p className="eyebrow">{showWizard ? "Configuration" : "Admin"}</p>
          <h1>{showWizard ? "First-run setup" : SECTION_TITLES[section] || "Admin"}</h1>
        </div>
        {showWizard ? (
          <Link to="/" className="btn-link">
            Back to chat
          </Link>
        ) : null}
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
                  Finish setup
                </button>
              )}
              <InlineAlert type={footerAlert?.type} message={footerAlert?.message} testId="wizard-footer-alert" />
            </div>
          </div>
        </>
      ) : (
        renderMaintenanceDashboard()
      )}

      {showWizard && appVersion ? (
        <p className="status status-secondary" data-testid="app-version">
          CuratorX {appVersion}
        </p>
      ) : null}

      {status ? <p className="status status-secondary">{status}</p> : null}
    </div>
  );
}

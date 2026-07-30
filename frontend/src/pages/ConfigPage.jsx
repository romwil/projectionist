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
  getLiveChannelsLifecycleStatus,
  getLiveChannelsPlexAttach,
  postLiveChannelsPlexAttachGuide,
  getLiveChannelsStarterPack,
  getLiveChannelsStatus,
  getLiveChannelsTunarrLogs,
  getPersona,
  getSettings,
  getWizardStatus,
  getPlexSections,
  listJobs,
  deleteUser,
  listUsers,
  patchUserDisabled,
  patchUserYouthMode,
  postLiveChannelsLifecycle,
  postLiveChannelsPreflight,
  publishLiveChannelsStarters,
  putPersona,
  putSystemConfig,
  resolveModelForProvider,
  revealSettingsSecret,
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
import { formatRemaining } from "../lib/onNow.js";
import {
  canToggleSecretVisibility,
  isSecretConfigured,
  secretPlaceholder,
  seerrSecretPlaceholder,
} from "../lib/secretField.js";

const ADMIN_SECTIONS = new Set([
  "overview",
  "connections",
  "libraries",
  "sync",
  "persona",
  "household",
  "seerr",
  "live-channels",
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
  "live-channels": "Live Channels",
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
    "Lets Projectionist read your Plex libraries (sync, collections, ratings). This is a server token for the Media Server — not the same as household Sign in with Plex on the login page.",
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

function settingsPayloadForTest(service, settings) {
  if (service === "seerr") {
    return {
      ...settings,
      seerr_url: settings.seerr?.url || "",
      seerr_api_key: settings.seerr?.api_key || "",
    };
  }
  if (service === "tunarr") {
    return {
      ...settings,
      tunarr_url: settings.tunarr?.url || "",
    };
  }
  return settings;
}

function SecretInput({
  field,
  settings,
  value,
  onChange,
  disabled = false,
  placeholder = "",
  visible = false,
  revealing = false,
  onToggleVisible,
}) {
  // Drafts reveal client-side; stored secrets load via owner-only reveal endpoint.
  const configured = isSecretConfigured(settings, field);
  const canReveal = canToggleSecretVisibility(value, { configured });
  const revealed = canReveal && visible && String(value ?? "").length > 0;
  return (
    <div className="secret-field">
      <input
        type={revealed ? "text" : "password"}
        value={value ?? ""}
        disabled={disabled || revealing}
        placeholder={placeholder || secretPlaceholder(settings, field)}
        onChange={onChange}
        autoComplete="off"
        data-testid={`secret-input-${field}`}
      />
      {canReveal ? (
        <button
          type="button"
          className="secret-toggle"
          data-testid={`secret-toggle-${field}`}
          aria-label={visible ? "Hide secret" : "Show secret"}
          aria-pressed={visible}
          disabled={disabled || revealing}
          onClick={onToggleVisible}
        >
          {revealing ? "…" : visible ? "Hide" : "Show"}
        </button>
      ) : null}
    </div>
  );
}

function InlineAlert({ type, message, details, testId }) {
  if (!message || (type !== "success" && type !== "error")) return null;
  const detailList = Array.isArray(details)
    ? details.map((item) => String(item || "").trim()).filter(Boolean)
    : [];
  return (
    <div
      className={`inline-alert inline-alert-${type}`}
      role="alert"
      data-testid={testId || `inline-alert-${type}`}
    >
      <div className="inline-alert-message">{message}</div>
      {detailList.length ? (
        <ul className="inline-alert-details" data-testid={`${testId || `inline-alert-${type}`}-details`}>
          {detailList.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function formatPublishFeedback(result) {
  const published = result?.count_published || 0;
  const skipped = result?.count_skipped || 0;
  const errors = result?.count_errors || 0;
  const summary = `Published ${published}, skipped ${skipped}, errors ${errors}.`;
  const details = (result?.errors || []).map((err) => {
    const label = [err?.number, err?.name].filter((part) => part != null && part !== "").join(" · ");
    return `${label || "Channel"}: ${err?.error || "unknown error"}`;
  });
  const type = errors > 0 || result?.ok === false ? "error" : "success";
  return { summary, details, type };
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
    case "tunarr":
      return Boolean(settings.features?.live_channels_enabled && settings.tunarr?.url);
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
  const [revealingSecret, setRevealingSecret] = useState(null);
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
  const [liveChannelsStatus, setLiveChannelsStatus] = useState(null);
  const [livePreflight, setLivePreflight] = useState(null);
  const [liveStarters, setLiveStarters] = useState(null);
  const [liveAttach, setLiveAttach] = useState(null);
  const [liveBusy, setLiveBusy] = useState(null);
  const [liveEngineProgress, setLiveEngineProgress] = useState(null);
  const [liveEngineError, setLiveEngineError] = useState("");
  const [selectedStarters, setSelectedStarters] = useState({});
  const [tunarrLogsOpen, setTunarrLogsOpen] = useState(false);
  const [tunarrLogs, setTunarrLogs] = useState(null);
  const [tunarrLogsBusy, setTunarrLogsBusy] = useState(false);
  const trackedSyncJobIdRef = useRef(null);
  const syncWasRunningRef = useRef(false);
  const enginePollRef = useRef(null);

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
    if (showWizard || section !== "live-channels") return;
    if (!settings?.features?.live_channels_enabled) {
      setLiveChannelsStatus(null);
      return;
    }
    getLiveChannelsStatus()
      .then(setLiveChannelsStatus)
      .catch(() => setLiveChannelsStatus(null));
    if (settings?.tunarr?.docker_orchestration) {
      getLiveChannelsLifecycleStatus()
        .then(setLiveEngineProgress)
        .catch(() => {});
    }
  }, [showWizard, section, settings?.features?.live_channels_enabled, settings?.tunarr?.url, settings?.tunarr?.docker_orchestration]);

  useEffect(() => {
    return () => {
      if (enginePollRef.current) {
        clearInterval(enginePollRef.current);
        enginePollRef.current = null;
      }
    };
  }, []);

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

  function updateTunarrSettings(patch) {
    setSettings((prev) => ({
      ...prev,
      tunarr: { ...(prev?.tunarr || {}), ...patch },
    }));
  }

  function updateYouthSettings(patch) {
    setSettings((prev) => ({
      ...prev,
      youth: { ...(prev?.youth || {}), ...patch },
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

  async function handleYouthModeToggle(entry) {
    try {
      await patchUserYouthMode(entry.id, !entry.is_youth);
      await refreshManagedUsers();
      setActionFeedback("users", "success", entry.is_youth ? "Youth mode removed." : "Youth mode enabled.");
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
    return (
      <SecretInput
        field={field}
        settings={settings}
        value={value}
        disabled={options.disabled}
        placeholder={seerrSecretPlaceholder(settings)}
        visible={Boolean(visibleSecrets[field])}
        revealing={revealingSecret === field}
        onToggleVisible={() => toggleSecretVisibility(field)}
        onChange={(event) => updateSeerrSettings({ api_key: event.target.value })}
      />
    );
  }

  async function toggleSecretVisibility(field) {
    const currentlyVisible = Boolean(visibleSecrets[field]);
    if (currentlyVisible) {
      setVisibleSecrets((prev) => ({ ...prev, [field]: false }));
      return;
    }

    const currentValue =
      field === "seerr.api_key" ? settings?.seerr?.api_key ?? "" : settings?.[field] ?? "";
    if (String(currentValue).length > 0) {
      setVisibleSecrets((prev) => ({ ...prev, [field]: true }));
      return;
    }

    if (!isSecretConfigured(settings, field)) {
      return;
    }

    setRevealingSecret(field);
    try {
      const result = await revealSettingsSecret(field);
      const secret = String(result?.value ?? "");
      if (!secret) {
        throw new Error("Secret is not configured");
      }
      if (field === "seerr.api_key") {
        updateSeerrSettings({ api_key: secret });
      } else {
        updateSettings({ [field]: secret });
      }
      setVisibleSecrets((prev) => ({ ...prev, [field]: true }));
    } catch (error) {
      const alertArea =
        field === "seerr.api_key"
          ? "seerr"
          : field === "plex_token"
            ? "plex"
            : field.endsWith("_api_key")
              ? field.replace(/_api_key$/, "")
              : "llm";
      setActionFeedback(alertArea, "error", error.message || "Could not reveal secret");
    } finally {
      setRevealingSecret(null);
    }
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
        revealing={revealingSecret === field}
        onToggleVisible={() => toggleSecretVisibility(field)}
        onChange={(event) => updateSettings({ [field]: event.target.value })}
      />
    );
  }

  function setActionFeedback(area, type, message, options = {}) {
    const details = Array.isArray(options.details) ? options.details : null;
    setActionAlert({ area, type, message, details });
    // Areas that render their own InlineAlert should not also fill the page footer
    // status line (that produced duplicate red bar + plain text).
    if (area === "live-channels" || area === "tunarr" || options.skipStatus) {
      setStatus("");
    } else {
      setStatus(message);
    }
  }

  async function refreshTunarrLogs() {
    setTunarrLogsBusy(true);
    try {
      const payload = await getLiveChannelsTunarrLogs(200);
      setTunarrLogs(payload);
    } catch (error) {
      setTunarrLogs({
        ok: false,
        text: "",
        source: "",
        message: error.message || "Could not load broadcast engine logs.",
      });
    } finally {
      setTunarrLogsBusy(false);
    }
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

  async function handleEphemeralCollectionGcToggle(enabled) {
    updateFeatureFlags({ ephemeral_collection_gc_enabled: enabled });
    try {
      await persistSettings({
        features: { ...(settings.features || {}), ephemeral_collection_gc_enabled: enabled },
      });
      setActionFeedback(
        "plex-sections",
        "success",
        enabled
          ? "Ephemeral collection cleanup is on — expired [Projectionist] movie-night shelves will be pruned."
          : "Ephemeral collection cleanup is off — expired agent shelves stay on Plex until you delete them.",
      );
    } catch (error) {
      setActionFeedback("plex-sections", "error", error.message);
    }
  }

  async function handleLiveChannelsEnabled(enabled) {
    if (
      !enabled &&
      !window.confirm(
        "Turn off Live Channels? On now hides for the household. If Docker management is on, the broadcast engine stops — your channel data stays on disk.",
      )
    ) {
      return;
    }
    clearActionFeedback("live-channels");
    updateFeatureFlags({ live_channels_enabled: enabled });
    setLiveBusy(enabled ? "enable" : "disable");
    try {
      await persistSettings({
        features: { ...(settings.features || {}), live_channels_enabled: enabled },
      });
      if (!enabled && settings?.tunarr?.docker_orchestration) {
        try {
          await postLiveChannelsLifecycle("stop");
        } catch {
          /* stop is best-effort on disable */
        }
      }
      if (enabled) {
        getLiveChannelsStatus().then(setLiveChannelsStatus).catch(() => {});
      } else {
        setLiveChannelsStatus(null);
        setLivePreflight(null);
        setLiveStarters(null);
        setLiveAttach(null);
        setLiveEngineProgress(null);
        setLiveEngineError("");
        stopEngineProgressPoll();
      }
    } catch (error) {
      updateFeatureFlags({ live_channels_enabled: !enabled });
      setActionFeedback("live-channels", "error", error.message);
    } finally {
      setLiveBusy(null);
    }
  }

  function stopEngineProgressPoll() {
    if (enginePollRef.current) {
      clearInterval(enginePollRef.current);
      enginePollRef.current = null;
    }
  }

  async function pollEngineProgressOnce() {
    try {
      const progress = await getLiveChannelsLifecycleStatus();
      setLiveEngineProgress(progress);
      if (progress?.ready) {
        setLiveEngineError("");
      } else if (progress?.phase === "error" && progress?.error) {
        setLiveEngineError(progress.error);
      }
      return progress;
    } catch {
      return null;
    }
  }

  async function startBroadcastEngine() {
    clearActionFeedback("live-channels");
    setLiveEngineError("");
    setLiveBusy("lifecycle");
    setLiveEngineProgress({
      phase: "pulling",
      percent: 15,
      message: "Pulling image",
      ready: false,
      busy: true,
      ok: true,
      determinate: true,
    });
    stopEngineProgressPoll();
    const startedAt = Date.now();
    const timeoutMs = 5 * 60 * 1000;
    enginePollRef.current = setInterval(() => {
      pollEngineProgressOnce().then((progress) => {
        if (!progress) return;
        if (progress.ready || progress.phase === "error" || Date.now() - startedAt > timeoutMs) {
          stopEngineProgressPoll();
        }
      });
    }, 1500);

    try {
      const result = await postLiveChannelsLifecycle("ensure_running");
      if (result.tunarr_url) {
        updateTunarrSettings({ url: result.tunarr_url });
      }
      if (!result.ok) {
        const message = result.message || "Broadcast engine failed to start.";
        setLiveEngineError(message);
        setLiveEngineProgress((prev) => ({
          ...(prev || {}),
          phase: "error",
          percent: 0,
          message,
          ready: false,
          busy: false,
          ok: false,
          error: message,
        }));
        setActionFeedback("live-channels", "error", message);
        stopEngineProgressPoll();
        setLiveBusy(null);
        return;
      }
      // Keep polling until Tunarr reports ready (logs marker or HTTP), up to ~5 min.
      const deadline = Date.now() + timeoutMs;
      let progress = await pollEngineProgressOnce();
      while (Date.now() < deadline) {
        if (progress?.ready) break;
        if (progress?.phase === "error") break;
        await new Promise((resolve) => setTimeout(resolve, 1500));
        progress = await pollEngineProgressOnce();
      }
      stopEngineProgressPoll();
      if (progress?.ready) {
        setActionFeedback(
          "live-channels",
          "success",
          progress.message || "Tunarr is ready!",
        );
      } else if (progress?.phase === "error") {
        setLiveEngineError(progress.error || progress.message || "Broadcast engine failed.");
        setActionFeedback("live-channels", "error", progress.error || progress.message);
      } else {
        const timeoutMsg =
          "Timed out waiting for Tunarr to become ready. Check Broadcast engine logs below.";
        setLiveEngineError(timeoutMsg);
        setLiveEngineProgress((prev) => ({
          ...(prev || {}),
          phase: "error",
          percent: prev?.percent || 80,
          message: timeoutMsg,
          ready: false,
          busy: false,
          ok: false,
          error: timeoutMsg,
        }));
        setActionFeedback("live-channels", "error", timeoutMsg);
      }
      const status = await getLiveChannelsStatus();
      setLiveChannelsStatus(status);
      if (result.tunarr_url) {
        await getSettings().then(setSettings).catch(() => {});
      }
    } catch (error) {
      stopEngineProgressPoll();
      const message = error.message || "Broadcast engine failed to start.";
      setLiveEngineError(message);
      setLiveEngineProgress((prev) => ({
        ...(prev || {}),
        phase: "error",
        percent: 0,
        message,
        ready: false,
        busy: false,
        ok: false,
        error: message,
      }));
      setActionFeedback("live-channels", "error", message);
    } finally {
      setLiveBusy(null);
    }
  }

  async function handleEphemeralCollectionGcDryRunToggle(enabled) {
    updateFeatureFlags({ ephemeral_collection_gc_dry_run: enabled });
    try {
      await persistSettings({
        features: { ...(settings.features || {}), ephemeral_collection_gc_dry_run: enabled },
      });
      setActionFeedback(
        "plex-sections",
        "success",
        enabled
          ? "Collection GC dry-run is on — the idle task logs what it would delete without removing anything."
          : "Collection GC dry-run is off — expired ephemeral collections will be deleted from Plex.",
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
      const message = "Setup complete. Welcome to Projectionist.";
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
            Point Projectionist at your language model, Plex server, Radarr, and Sonarr. Hit Verify on each
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
          Plex is connected. Select which movie and TV libraries Projectionist should index. You can change
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
      const filename = match?.[1] || "projectionist-training-corpus.json";
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
            Refresh Projectionist from your Plex libraries. The first sync can take a few minutes while titles
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
              {libraryStats.last_sync
                ? ` · Last synced ${formatLastSync(libraryStats.last_sync)}`
                : syncingLibrary
                  ? " · Syncing…"
                  : " · Never synced"}
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
              When enabled, people open Projectionist via <strong>Sign in with Plex</strong> (plex.tv PIN / link
              on the login page). The first account becomes owner; later accounts join via an invite link
              from <strong>Admin → Access</strong> (invite-only by default). This is separate from the Plex{" "}
              <em>server</em> token above used for library sync.
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
            <label className="config-toggle" data-testid="guest-tour-enabled-toggle">
              <input
                type="checkbox"
                checked={Boolean(settings?.features?.guest_tour_enabled)}
                onChange={(event) => {
                  const enabled = event.target.checked;
                  updateFeatureFlags({ guest_tour_enabled: enabled });
                  persistSettings({
                    features: { ...(settings.features || {}), guest_tour_enabled: enabled },
                  })
                    .then(() =>
                      setActionFeedback(
                        "guest-tour",
                        "success",
                        enabled
                          ? "Take a Tour is on — visitors see it on the login page."
                          : "Take a Tour is off.",
                      ),
                    )
                    .catch((error) => setActionFeedback("guest-tour", "error", error.message));
                }}
              />
              <span>Enable public Take a Tour (/tour)</span>
            </label>
            <p className="wizard-note">
              Optional. Env <code>CURATORX_GUEST_TOUR_ENABLED</code> overrides this toggle when set.
            </p>
            {settings?.features?.multi_user_enabled ? (
              <>
                <label className="config-toggle" data-testid="agent-may-mutate-personal-data-toggle">
                  <input
                    type="checkbox"
                    checked={Boolean(settings?.features?.agent_may_mutate_personal_data)}
                    onChange={(event) => {
                      const enabled = event.target.checked;
                      updateFeatureFlags({ agent_may_mutate_personal_data: enabled });
                      persistSettings({
                        features: {
                          ...(settings.features || {}),
                          agent_may_mutate_personal_data: enabled,
                        },
                      });
                    }}
                  />
                  <span>Agent may mutate personal data</span>
                </label>
                <p className="wizard-note">
                  When multi-user is on, chat tools that pin watchlist items, edit lists, save reviews, or
                  write memory stay off unless you enable this. *arr / Seerr / collections still require a
                  confirm token either way.
                </p>
              </>
            ) : null}
            {settings?.features?.multi_user_enabled ? (
              <>
                <label className="config-toggle" data-testid="invite-only-toggle">
                  <input
                    type="checkbox"
                    checked={settings?.features?.invite_only !== false}
                    onChange={(event) => {
                      const enabled = event.target.checked;
                      updateFeatureFlags({ invite_only: enabled });
                      persistSettings({
                        features: { ...(settings.features || {}), invite_only: enabled },
                      })
                        .then(() =>
                          setActionFeedback(
                            "invite-only",
                            "success",
                            enabled
                              ? "Invite-only join is on — new Plex/SSO users need a /join link."
                              : "Invite-only is off — new sign-ins can auto-provision (unless open auto-provision is also considered).",
                          ),
                        )
                        .catch((error) => setActionFeedback("invite-only", "error", error.message));
                    }}
                  />
                  <span>Require invite to join (recommended)</span>
                </label>
                <label className="config-toggle" data-testid="open-auto-provision-toggle">
                  <input
                    type="checkbox"
                    checked={Boolean(settings?.features?.open_auto_provision)}
                    onChange={(event) => {
                      const enabled = event.target.checked;
                      updateFeatureFlags({ open_auto_provision: enabled });
                      persistSettings({
                        features: { ...(settings.features || {}), open_auto_provision: enabled },
                      })
                        .then(() =>
                          setActionFeedback(
                            "open-auto-provision",
                            "success",
                            enabled
                              ? "Open auto-provision is on — anyone who can reach sign-in becomes a member (pre-1.26 LAN behavior)."
                              : "Open auto-provision is off — invite-only applies when Require invite is on.",
                          ),
                        )
                        .catch((error) =>
                          setActionFeedback("open-auto-provision", "error", error.message),
                        );
                    }}
                  />
                  <span>Open auto-provision (LAN-open; opt-in)</span>
                </label>
                <p className="wizard-note field-help">
                  Default is invite-only. Create links under <strong>Admin → Access</strong>. Turn on{" "}
                  <em>Open auto-provision</em> only if you want any reachable Plex/SSO identity to join
                  without an invite.
                </p>
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
                              <th scope="col">Youth mode</th>
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
                                    <button
                                      type="button"
                                      className="ghost"
                                      data-testid={`user-youth-mode-${entry.id}`}
                                      disabled={isSelf}
                                      onClick={() => handleYouthModeToggle(entry)}
                                    >
                                      {entry.is_youth ? "Youth mode on" : "Set Youth mode"}
                                    </button>
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
                <label className="config-field" data-testid="youth-max-rating-field">
                  <span>Youth max content rating</span>
                  <select
                    value={settings?.youth?.max_content_rating || "PG-13"}
                    onChange={(event) => {
                      const max_content_rating = event.target.value;
                      updateYouthSettings({ max_content_rating });
                      persistSettings({
                        youth: { ...(settings.youth || {}), max_content_rating },
                      })
                        .then(() =>
                          setActionFeedback(
                            "users",
                            "success",
                            `Youth max rating set to ${max_content_rating}. Unrated titles stay hidden.`,
                          ),
                        )
                        .catch((error) => setActionFeedback("users", "error", error.message));
                    }}
                    data-testid="youth-max-rating"
                  >
                    {["G", "PG", "PG-13", "R", "TV-Y", "TV-Y7", "TV-G", "TV-PG", "TV-14"].map((rating) => (
                      <option key={rating} value={rating}>
                        {rating}
                      </option>
                    ))}
                  </select>
                  <span className="wizard-note">
                    Youth-mode accounts never see empty ratings or anything above this max (fail-closed).
                  </span>
                </label>
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

        {!showWizard && showSection("live-channels") ? (
          <section
            className="config-section live-channels-section"
            data-testid="live-channels-settings"
            data-enabled={settings?.features?.live_channels_enabled ? "true" : "false"}
          >
            {!settings?.features?.live_channels_enabled ? (
              <div className="live-channels-hero" data-testid="live-channels-enabled-toggle">
                <p className="eyebrow">Live Channels</p>
                <h2>Your library, on the air</h2>
                <p className="live-channels-hero-lede">
                  Projectionist builds stations from titles you already own and adds them to Plex Live TV
                  as another tuner — alongside any OTA antenna setup you already have. The household
                  watches where they already do.
                </p>
                <div className="wizard-actions">
                  <button
                    type="button"
                    data-testid="live-channels-enable-cta"
                    disabled={liveBusy === "enable" || liveBusy === "disable"}
                    aria-busy={liveBusy === "enable"}
                    onClick={() => handleLiveChannelsEnabled(true)}
                  >
                    {liveBusy === "enable" ? "Turning on…" : "Let's go"}
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div
                  className="live-channels-on-banner"
                  data-testid="live-channels-enabled-toggle"
                  role="status"
                  aria-live="polite"
                >
                  <div className="live-channels-on-copy">
                    <p className="eyebrow">Live Channels</p>
                    <h2>Live Channels is on</h2>
                    <p className="live-channels-hero-lede">
                      Finish the steps below to add Tunarr beside any existing OTA tuner in Plex Live TV.
                      Watching stays in Plex — nothing replaces your antenna DVR.
                    </p>
                  </div>
                  <button
                    type="button"
                    className="ghost"
                    data-testid="live-channels-disable-cta"
                    disabled={liveBusy === "enable" || liveBusy === "disable"}
                    aria-busy={liveBusy === "disable"}
                    onClick={() => handleLiveChannelsEnabled(false)}
                  >
                    {liveBusy === "disable" ? "Turning off…" : "Turn off"}
                  </button>
                </div>

                <div className="live-channels-journey">
                  <div className="service-card" data-testid="live-channels-health-strip">
                    <div className="service-card-header">
                      <div className="service-card-title">
                        <h3>What's on the air</h3>
                      </div>
                      <button
                        type="button"
                        className="ghost"
                        data-testid="live-channels-refresh-status"
                        disabled={liveBusy === "status"}
                        onClick={() => {
                          setLiveBusy("status");
                          getLiveChannelsStatus()
                            .then(setLiveChannelsStatus)
                            .catch((error) => setActionFeedback("live-channels", "error", error.message))
                            .finally(() => setLiveBusy(null));
                        }}
                      >
                        Refresh
                      </button>
                    </div>
                    <p className="wizard-note">
                      A quick pulse on the broadcast engine, stations, and anything airing right now.
                    </p>
                    <p className="wizard-note" data-testid="live-channels-health-summary">
                      {liveChannelsStatus
                        ? [
                            liveChannelsStatus.broadcast?.sidecar_up
                              ? "Broadcast engine running"
                              : "Broadcast engine unreachable",
                            `${liveChannelsStatus.channel_count ?? 0} station(s)`,
                            liveChannelsStatus.airing?.length
                              ? `${liveChannelsStatus.airing.length} airing now`
                              : null,
                            liveChannelsStatus.sessions?.total_connections
                              ? `${liveChannelsStatus.sessions.total_connections} viewer connection(s)`
                              : null,
                            liveChannelsStatus.last_publish_at
                              ? `Last lineup publish ${liveChannelsStatus.last_publish_at}`
                              : "No lineup published yet",
                          ]
                            .filter(Boolean)
                            .join(" · ")
                        : "Status not loaded yet — hit Refresh after you connect."}
                    </p>
                    {liveChannelsStatus?.last_error && actionAlert?.area !== "live-channels" ? (
                      <InlineAlert
                        type="error"
                        message={liveChannelsStatus.last_error}
                        testId="live-channels-last-error"
                      />
                    ) : null}
                    {liveChannelsStatus?.airing?.length ? (
                      <ul className="wizard-note" data-testid="live-channels-airing-progress">
                        {liveChannelsStatus.airing.slice(0, 6).map((row) => {
                          const label =
                            row.number != null ? `${row.number} · ${row.name}` : row.name;
                          const pct =
                            row.percent == null || !Number.isFinite(Number(row.percent))
                              ? null
                              : `${Math.round(Number(row.percent))}%`;
                          const remaining = formatRemaining(row.seconds_remaining);
                          return (
                            <li key={row.id || label}>
                              {label}: {row.title}
                              {pct ? ` — ${pct}` : ""}
                              {remaining ? ` (${remaining})` : ""}
                              {row.is_paused ? " · paused" : ""}
                            </li>
                          );
                        })}
                      </ul>
                    ) : null}
                  </div>

                  <div
                    className={`service-card ${testResults.tunarr?.state === "success" ? "service-ok" : ""} ${testing === "tunarr" ? "service-loading" : ""} ${testResults.tunarr?.state === "error" ? "service-error" : ""}`}
                  >
                    <div className="service-card-header">
                      <div className="service-card-title">
                        <h3>Broadcast engine connection</h3>
                        <CertifiedBadge
                          certified={certifications.tunarr?.certified}
                          testing={testing === "tunarr"}
                          serviceId="tunarr"
                        />
                      </div>
                      <button
                        type="button"
                        data-testid="verify-tunarr"
                        onClick={async () => {
                          clearActionFeedback("live-channels");
                          await runTest("tunarr");
                        }}
                        disabled={testing === "tunarr" || !settings?.tunarr?.url}
                      >
                        {testing === "tunarr" ? "Testing…" : "Test connection"}
                      </button>
                    </div>
                    <p className="wizard-note">
                      Point Projectionist at Tunarr (the engine behind your stations). Most owners leave the URL
                      as-is once Docker has started it.
                    </p>
                    <div className="service-fields">
                      <label>
                        <span>Tunarr base URL</span>
                        <input
                          type="text"
                          data-testid="tunarr-url"
                          value={settings?.tunarr?.url ?? ""}
                          placeholder="http://host.docker.internal:8000"
                          onChange={(event) => updateTunarrSettings({ url: event.target.value })}
                          onBlur={() =>
                            persistSettings({
                              tunarr: { ...(settings.tunarr || {}), url: settings?.tunarr?.url ?? "" },
                            }).catch((error) => setActionFeedback("live-channels", "error", error.message))
                          }
                        />
                      </label>
                    </div>
                    <details className="live-channels-advanced">
                      <summary>Advanced</summary>
                      <div className="service-fields">
                        <label>
                          <span>Pinned image tag</span>
                          <input
                            type="text"
                            data-testid="tunarr-image-tag"
                            value={settings?.tunarr?.image_tag ?? "chrisbenincasa/tunarr:1.3.9"}
                            onChange={(event) => updateTunarrSettings({ image_tag: event.target.value })}
                            onBlur={() =>
                              persistSettings({
                                tunarr: {
                                  ...(settings.tunarr || {}),
                                  image_tag:
                                    settings?.tunarr?.image_tag ?? "chrisbenincasa/tunarr:1.3.9",
                                },
                              }).catch((error) =>
                                setActionFeedback("live-channels", "error", error.message),
                              )
                            }
                          />
                        </label>
                      </div>
                      <label className="config-toggle" data-testid="tunarr-docker-orchestration">
                        <input
                          type="checkbox"
                          checked={Boolean(settings?.tunarr?.docker_orchestration)}
                          onChange={(event) => {
                            const orchEnabled = event.target.checked;
                            updateTunarrSettings({ docker_orchestration: orchEnabled });
                            persistSettings({
                              tunarr: { ...(settings.tunarr || {}), docker_orchestration: orchEnabled },
                            }).catch((error) =>
                              setActionFeedback("live-channels", "error", error.message),
                            );
                          }}
                        />
                        <span>
                          Let Projectionist start and stop Tunarr with Docker (needs the Docker socket and
                          PROJECTIONIST_DOCKER_ORCHESTRATION=1 on the host).
                        </span>
                      </label>
                    </details>
                    {testResults.tunarr?.message &&
                    actionAlert?.area !== "live-channels" &&
                    actionAlert?.area !== "tunarr" ? (
                      <InlineAlert
                        type={testResults.tunarr.state}
                        message={testResults.tunarr.message}
                        testId="live-channels-tunarr-test-alert"
                      />
                    ) : null}
                    {actionAlert?.area === "tunarr" ? (
                      <InlineAlert
                        type={actionAlert.type}
                        message={actionAlert.message}
                        details={actionAlert.details}
                        testId="live-channels-tunarr-action-alert"
                      />
                    ) : null}
                  </div>

                  <div className="service-card" data-testid="live-channels-preflight">
                    <div className="service-card-header">
                      <div className="service-card-title">
                        <p className="live-channels-step-label">Step 1</p>
                        <h3>Check you're ready</h3>
                      </div>
                      <button
                        type="button"
                        data-testid="live-channels-run-preflight"
                        disabled={liveBusy === "preflight"}
                        onClick={async () => {
                          setLiveBusy("preflight");
                          try {
                            const result = await postLiveChannelsPreflight({
                              plex_pass_confirmed: Boolean(settings?.tunarr?.plex_pass_confirmed),
                            });
                            setLivePreflight(result);
                            const hardFails = (result.checks || [])
                              .filter((check) => !check.ok && !check.soft)
                              .map((check) => `${check.label}: ${check.message}`);
                            setActionFeedback(
                              "live-channels",
                              result.ready ? "success" : "error",
                              result.summary || "Ready check finished.",
                              { details: hardFails },
                            );
                          } catch (error) {
                            setActionFeedback("live-channels", "error", error.message);
                          } finally {
                            setLiveBusy(null);
                          }
                        }}
                      >
                        {liveBusy === "preflight" ? "Checking…" : "Run ready check"}
                      </button>
                    </div>
                    <label className="config-toggle" data-testid="live-channels-plex-pass-confirm">
                      <input
                        type="checkbox"
                        checked={Boolean(settings?.tunarr?.plex_pass_confirmed)}
                        onChange={(event) => {
                          const confirmed = event.target.checked;
                          updateTunarrSettings({ plex_pass_confirmed: confirmed });
                          persistSettings({
                            tunarr: { ...(settings.tunarr || {}), plex_pass_confirmed: confirmed },
                          }).catch((error) => setActionFeedback("live-channels", "error", error.message));
                        }}
                      />
                      <span>
                        I have an active Plex Pass (needed for Live TV / DVR). Projectionist can't check this
                        for you.
                      </span>
                    </label>
                    {livePreflight?.checks?.length ? (
                      <ul className="wizard-note" data-testid="live-channels-preflight-list">
                        {livePreflight.checks.map((check) => (
                          <li key={check.id}>
                            {check.ok ? "✓" : check.soft ? "○" : "✗"} {check.label}: {check.message}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="wizard-note">
                        Looks for Docker, free disk, a reachable Plex, your Tunarr URL, and the Plex Pass
                        confirmation above.
                      </p>
                    )}
                  </div>

                  {settings?.tunarr?.docker_orchestration ? (
                    <div className="service-card" data-testid="live-channels-lifecycle">
                      <div className="service-card-header">
                        <div className="service-card-title">
                          <p className="live-channels-step-label">Step 2</p>
                          <h3>Start the broadcast engine</h3>
                          {liveEngineProgress?.ready ? (
                            <span
                              className="certified-badge certified-badge-ok"
                              data-testid="live-channels-engine-ready"
                            >
                              ✓ Tunarr is ready
                            </span>
                          ) : null}
                        </div>
                        <button
                          type="button"
                          data-testid="live-channels-ensure-running"
                          disabled={liveBusy === "lifecycle"}
                          onClick={() => {
                            startBroadcastEngine().catch(() => {});
                          }}
                        >
                          {liveBusy === "lifecycle"
                            ? "Starting…"
                            : liveEngineProgress?.ready
                              ? "Restart engine"
                              : "Start engine"}
                        </button>
                      </div>
                      <p className="wizard-note">
                        Pulls the pinned Docker image and starts Tunarr with a config volume under your data
                        directory. Turning Live Channels off later stops the container but keeps that volume.
                      </p>
                      {liveBusy === "lifecycle" ||
                      (liveEngineProgress &&
                        liveEngineProgress.phase &&
                        liveEngineProgress.phase !== "idle" &&
                        !liveEngineProgress.ready) ||
                      liveEngineProgress?.ready ? (
                        <div
                          className="live-channels-engine-progress"
                          data-testid="live-channels-engine-progress"
                        >
                          {liveEngineProgress?.ready ? (
                            <ul
                              className="wizard-note live-channels-engine-checks"
                              data-testid="live-channels-engine-ready-list"
                            >
                              <li>✓ Broadcast engine: Tunarr is ready</li>
                              {liveEngineProgress.http_ready ? (
                                <li>✓ API health: responding</li>
                              ) : null}
                              {liveEngineProgress.logs_ready ? (
                                <li>✓ Startup log: “Tunarr is ready!”</li>
                              ) : null}
                            </ul>
                          ) : (
                            <>
                              <p className="live-channels-engine-progress-headline">
                                {liveEngineProgress?.message ||
                                  (liveBusy === "lifecycle" ? "Starting broadcast engine…" : "Working…")}
                              </p>
                              <div
                                className={`live-channels-engine-progress-bar${
                                  liveBusy === "lifecycle" &&
                                  !(liveEngineProgress?.percent > 0)
                                    ? " is-indeterminate"
                                    : ""
                                }`}
                                role="progressbar"
                                aria-valuemin={0}
                                aria-valuemax={100}
                                aria-valuenow={
                                  Number.isFinite(liveEngineProgress?.percent)
                                    ? liveEngineProgress.percent
                                    : undefined
                                }
                                aria-label="Broadcast engine start progress"
                              >
                                <span
                                  className="live-channels-engine-progress-fill"
                                  style={{
                                    width: `${Math.max(
                                      8,
                                      Math.min(100, Number(liveEngineProgress?.percent) || 15),
                                    )}%`,
                                  }}
                                />
                              </div>
                              <p className="wizard-note live-channels-engine-phase">
                                {liveEngineProgress?.phase === "pulling"
                                  ? "Pulling image"
                                  : liveEngineProgress?.phase === "creating"
                                    ? "Creating container"
                                    : liveEngineProgress?.phase === "starting"
                                      ? "Starting"
                                      : liveEngineProgress?.phase === "waiting_ready"
                                        ? "Waiting for Tunarr ready"
                                        : liveEngineProgress?.phase === "error"
                                          ? "Failed"
                                          : "Working…"}
                                {Number.isFinite(liveEngineProgress?.percent)
                                  ? ` · ${liveEngineProgress.percent}%`
                                  : ""}
                              </p>
                            </>
                          )}
                          {liveEngineError ? (
                            <div
                              className="inline-alert inline-alert-error"
                              data-testid="live-channels-engine-error"
                              role="alert"
                            >
                              <span className="inline-alert-message">{liveEngineError}</span>
                            </div>
                          ) : null}
                        </div>
                      ) : liveEngineError ? (
                        <div
                          className="inline-alert inline-alert-error"
                          data-testid="live-channels-engine-error"
                          role="alert"
                        >
                          <span className="inline-alert-message">{liveEngineError}</span>
                        </div>
                      ) : null}
                    </div>
                  ) : null}

                  <div className="service-card" data-testid="live-channels-starters">
                    <div className="service-card-header">
                      <div className="service-card-title">
                        <p className="live-channels-step-label">
                          Step {settings?.tunarr?.docker_orchestration ? "3" : "2"}
                        </p>
                        <h3>Propose starter stations</h3>
                      </div>
                      <button
                        type="button"
                        className="ghost"
                        data-testid="live-channels-load-starters"
                        disabled={liveBusy === "starters"}
                        onClick={async () => {
                          setLiveBusy("starters");
                          try {
                            const pack = await getLiveChannelsStarterPack();
                            setLiveStarters(pack);
                            const next = {};
                            for (const proposal of pack.proposals || []) {
                              next[`${proposal.number}:${proposal.name}`] = true;
                            }
                            setSelectedStarters(next);
                          } catch (error) {
                            setActionFeedback("live-channels", "error", error.message);
                          } finally {
                            setLiveBusy(null);
                          }
                        }}
                      >
                        {liveBusy === "starters" ? "Loading…" : "Propose starters"}
                      </button>
                    </div>
                    {liveStarters?.proposals?.length ? (
                      <>
                        <ul className="wizard-note" data-testid="live-channels-starter-list">
                          {liveStarters.proposals.map((proposal) => {
                            const key = `${proposal.number}:${proposal.name}`;
                            return (
                              <li key={key}>
                                <label className="config-toggle">
                                  <input
                                    type="checkbox"
                                    checked={Boolean(selectedStarters[key])}
                                    onChange={(event) =>
                                      setSelectedStarters((prev) => ({
                                        ...prev,
                                        [key]: event.target.checked,
                                      }))
                                    }
                                  />
                                  <span>
                                    {proposal.number} · {proposal.name}
                                    {proposal.summary ? ` — ${proposal.summary}` : ""}
                                  </span>
                                </label>
                              </li>
                            );
                          })}
                        </ul>
                        <div className="wizard-actions">
                          <button
                            type="button"
                            data-testid="live-channels-publish-starters"
                            disabled={liveBusy === "publish"}
                            onClick={async () => {
                              if (
                                !window.confirm(
                                  "Publish the selected starter stations? Existing channel numbers are skipped.",
                                )
                              ) {
                                return;
                              }
                              setLiveBusy("publish");
                              try {
                                const recipes = (liveStarters.proposals || []).filter((proposal) => {
                                  const key = `${proposal.number}:${proposal.name}`;
                                  return selectedStarters[key];
                                });
                                const result = await publishLiveChannelsStarters({ recipes });
                                const feedback = formatPublishFeedback(result);
                                setActionFeedback(
                                  "live-channels",
                                  feedback.type,
                                  feedback.summary,
                                  { details: feedback.details },
                                );
                                const status = await getLiveChannelsStatus();
                                setLiveChannelsStatus(status);
                              } catch (error) {
                                setActionFeedback("live-channels", "error", error.message);
                              } finally {
                                setLiveBusy(null);
                              }
                            }}
                          >
                            {liveBusy === "publish" ? "Publishing…" : "Publish starters"}
                          </button>
                        </div>
                      </>
                    ) : (
                      <p className="wizard-note">
                        Suggest 2–4 stations from your taste clusters, motifs, and collections (plus a Chaos /
                        youth-safe option when it fits).
                      </p>
                    )}
                  </div>

                  <div className="service-card" data-testid="live-channels-plex-attach">
                    <div className="service-card-header">
                      <div className="service-card-title">
                        <p className="live-channels-step-label">
                          Step {settings?.tunarr?.docker_orchestration ? "4" : "3"}
                        </p>
                        <h3>Add Tunarr beside your tuners in Plex</h3>
                      </div>
                      <div className="service-card-actions">
                        <button
                          type="button"
                          className="ghost"
                          data-testid="live-channels-load-attach"
                          disabled={liveBusy === "attach" || liveBusy === "attach-guide"}
                          onClick={async () => {
                            setLiveBusy("attach");
                            try {
                              setLiveAttach(await getLiveChannelsPlexAttach());
                            } catch (error) {
                              setActionFeedback("live-channels", "error", error.message);
                            } finally {
                              setLiveBusy(null);
                            }
                          }}
                        >
                          {liveBusy === "attach" ? "Loading…" : "Show Plex steps"}
                        </button>
                        <button
                          type="button"
                          className="primary"
                          data-testid="live-channels-attach-guide"
                          disabled={
                            liveBusy === "attach" ||
                            liveBusy === "attach-guide" ||
                            Boolean(liveAttach?.needs_lan_url)
                          }
                          onClick={async () => {
                            setLiveBusy("attach-guide");
                            try {
                              if (!liveAttach) {
                                setLiveAttach(await getLiveChannelsPlexAttach());
                              }
                              const result = await postLiveChannelsPlexAttachGuide();
                              setActionFeedback(
                                "live-channels",
                                "success",
                                result.message ||
                                  "Tunarr XMLTV guide attached in Plex (OTA left alone).",
                              );
                            } catch (error) {
                              setActionFeedback("live-channels", "error", error.message);
                            } finally {
                              setLiveBusy(null);
                            }
                          }}
                        >
                          {liveBusy === "attach-guide"
                            ? "Attaching guide…"
                            : "Attach Tunarr guide in Plex"}
                        </button>
                      </div>
                    </div>
                    {liveAttach ? (
                      <>
                        <p
                          className="wizard-note live-channels-coexist-note"
                          data-testid="live-channels-coexist-note"
                        >
                          {liveAttach.existing_livetv?.message ||
                            liveAttach.coexistence?.note ||
                            "Plex supports multiple tuners — add Tunarr alongside any OTA setup; do not remove existing Live TV."}
                        </p>
                        {liveAttach.coexistence?.guide_warning ? (
                          <p
                            className="wizard-note live-channels-guide-warning"
                            data-testid="live-channels-guide-warning"
                          >
                            {liveAttach.coexistence.guide_warning}
                          </p>
                        ) : null}
                        <ol className="wizard-note" data-testid="live-channels-attach-steps">
                          {(liveAttach.steps || []).map((step) => (
                            <li key={step.title}>
                              <strong>{step.title}</strong> — {step.body}
                            </li>
                          ))}
                        </ol>
                        {liveAttach.needs_lan_url || !liveAttach.tuner_url ? (
                          <p className="wizard-note" data-testid="live-channels-attach-warning">
                            {liveAttach.warning ||
                              "Set a LAN Tunarr address before pasting into Plex. Projectionist uses host.docker.internal only for its own connection to Tunarr — Plex cannot resolve that name."}
                          </p>
                        ) : (
                          <div className="service-fields">
                            <label>
                              <span>
                                Network address (host:port) — only if Plex did not discover Tunarr
                              </span>
                              <input
                                type="text"
                                readOnly
                                data-testid="live-channels-manual-address"
                                value={liveAttach.manual_address || ""}
                                onFocus={(event) => event.target.select()}
                              />
                            </label>
                            <label>
                              <span>Tuner base URL (reference)</span>
                              <input
                                type="text"
                                readOnly
                                data-testid="live-channels-tuner-url"
                                value={liveAttach.tuner_url || ""}
                                onFocus={(event) => event.target.select()}
                              />
                            </label>
                            <label>
                              <span>
                                Tunarr XMLTV URL (used by Attach Tunarr guide in Plex — not a
                                Plex UI paste field)
                              </span>
                              <input
                                type="text"
                                readOnly
                                data-testid="live-channels-guide-url"
                                value={liveAttach.guide_url || ""}
                                onFocus={(event) => event.target.select()}
                              />
                            </label>
                          </div>
                        )}
                        <p className="wizard-note">
                          {liveAttach.discovery?.ok ? "✓" : "○"}{" "}
                          {liveAttach.discovery?.message || "Discovery not checked."}
                        </p>
                      </>
                    ) : (
                      <p className="wizard-note">
                        On Tuner Setup, select discovered Tunarr and enter any ZIP so Next unlocks.
                        EPG Location is commercial lineups only. Then click Attach Tunarr guide in
                        Plex — Projectionist wires Tunarr XMLTV via the PMS API (OTA stays on its
                        commercial guide). Leave any OTA device in place.
                      </p>
                    )}
                  </div>

                  <details
                    className="live-channels-logs"
                    data-testid="live-channels-tunarr-logs"
                    open={tunarrLogsOpen}
                    onToggle={(event) => {
                      const open = event.currentTarget.open;
                      setTunarrLogsOpen(open);
                      if (open && !tunarrLogs && !tunarrLogsBusy) {
                        refreshTunarrLogs();
                      }
                    }}
                  >
                    <summary data-testid="live-channels-tunarr-logs-summary">
                      Broadcast engine logs
                    </summary>
                    <div className="live-channels-logs-toolbar">
                      <p className="wizard-note">
                        Recent Tunarr output (last 200 lines). Useful when Publish starters or Start
                        engine fails.
                      </p>
                      <button
                        type="button"
                        className="ghost"
                        data-testid="live-channels-tunarr-logs-refresh"
                        disabled={tunarrLogsBusy}
                        onClick={() => refreshTunarrLogs()}
                      >
                        {tunarrLogsBusy ? "Loading…" : "Refresh"}
                      </button>
                    </div>
                    {tunarrLogsBusy && !tunarrLogs ? (
                      <p className="wizard-note" data-testid="live-channels-tunarr-logs-loading">
                        Loading logs…
                      </p>
                    ) : null}
                    {tunarrLogs && !tunarrLogs.ok ? (
                      <InlineAlert
                        type="error"
                        message={tunarrLogs.message || "Logs unavailable."}
                        testId="live-channels-tunarr-logs-error"
                      />
                    ) : null}
                    {tunarrLogs?.ok ? (
                      <>
                        <p className="wizard-note" data-testid="live-channels-tunarr-logs-source">
                          Source: {tunarrLogs.source === "docker" ? "Docker container" : "Tunarr API"}
                          {tunarrLogs.message ? ` — ${tunarrLogs.message}` : ""}
                        </p>
                        <pre
                          className="live-channels-logs-scroller"
                          data-testid="live-channels-tunarr-logs-text"
                        >
                          {tunarrLogs.text || "(empty)"}
                        </pre>
                      </>
                    ) : null}
                  </details>
                </div>
              </>
            )}

            {actionAlert?.area === "live-channels" ? (
              <InlineAlert
                type={actionAlert.type}
                message={actionAlert.message}
                details={actionAlert.details}
                testId="live-channels-action-alert"
              />
            ) : null}
          </section>
        ) : null}

        {showSection("libraries") ? (
        <section className="config-section" data-testid="plex-library-mapping">
          <h2>Plex libraries</h2>
          <p className="wizard-note">Choose which movie and TV libraries Projectionist indexes. Update these if you rename or add libraries in Plex.</p>
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
            A 1–5 star review in Projectionist becomes the matching Plex rating (2, 4, 6, 8, or 10).
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
            Agent / movie-night shelves are tagged with a <code>[Projectionist]</code> prefix and expire after the TTL below.
          </p>
          <label className="config-toggle" data-testid="ephemeral-collection-gc-toggle">
            <input
              type="checkbox"
              checked={settings?.features?.ephemeral_collection_gc_enabled !== false}
              onChange={(event) => handleEphemeralCollectionGcToggle(event.target.checked)}
              disabled={!settings?.features?.plex_collections_enabled}
            />
            <span>Auto-clean expired Projectionist movie-night collections</span>
          </label>
          <label className="config-toggle" data-testid="ephemeral-collection-gc-dry-run-toggle">
            <input
              type="checkbox"
              checked={Boolean(settings?.features?.ephemeral_collection_gc_dry_run)}
              onChange={(event) => handleEphemeralCollectionGcDryRunToggle(event.target.checked)}
              disabled={
                !settings?.features?.plex_collections_enabled ||
                settings?.features?.ephemeral_collection_gc_enabled === false
              }
            />
            <span>Dry-run only (log what would be deleted)</span>
          </label>
          <label>
            <span>Ephemeral collection TTL (hours)</span>
            <input
              type="number"
              min={1}
              data-testid="ephemeral-collection-ttl-hours"
              value={settings?.ephemeral_collection_ttl_hours ?? 168}
              onChange={(event) => {
                const next = Math.max(1, Number(event.target.value) || 168);
                updateSettings({ ephemeral_collection_ttl_hours: next });
              }}
              onBlur={() =>
                persistSettings({
                  ephemeral_collection_ttl_hours: Math.max(
                    1,
                    Number(settings?.ephemeral_collection_ttl_hours) || 168,
                  ),
                }).catch((error) => setActionFeedback("plex-sections", "error", error.message))
              }
              disabled={!settings?.features?.plex_collections_enabled}
            />
          </label>
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
            Projectionist {appVersion}
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
          Projectionist {appVersion}
        </p>
      ) : null}

      {status ? <p className="status status-secondary">{status}</p> : null}
    </div>
  );
}

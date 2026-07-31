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
  deleteLiveChannelsChannel,
  getLiveChannelsCraftOptions,
  getLiveChannelsContinuityStatus,
  getLiveChannelsLifecycleStatus,
  getLiveChannelsPublishStatus,
  getLiveChannelsPlexAttach,
  postLiveChannelsPlexAttachGuide,
  postLiveChannelsPlexRepair,
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
  patchLiveChannelsEngineSettings,
  patchLiveChannelsStationSettings,
  patchUserDisabled,
  patchUserYouthMode,
  postLiveChannelsContinuityRepair,
  postLiveChannelsLifecycle,
  postLiveChannelsPreflight,
  previewLiveChannelsCraft,
  publishLiveChannelsChannel,
  publishLiveChannelsFromCollection,
  publishLiveChannelsStarters,
  refillLiveChannelsChannel,
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
import { liveChannelsStartTimeoutAlertType } from "../lib/liveChannelsEngineFeedback.js";
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
  const updated = result?.count_programming_updated || 0;
  const matched = result?.matched;
  const matchTotal = result?.match_total;
  const lineup = result?.lineup_programs ?? result?.program_count;
  const plexSync = result?.plex_sync;
  const parts = [`Published ${published}`, `skipped ${skipped}`, `errors ${errors}`];
  if (updated) parts.push(`lineups refreshed ${updated}`);
  if (matchTotal > 0) {
    parts.push(`matched ${matched ?? 0}/${matchTotal}`);
  }
  if (lineup != null && lineup !== "") {
    parts.push(`lineup ${lineup} programs`);
  }
  if (plexSync && plexSync.skipped !== true) {
    const mapped = plexSync.mapped;
    const expected = plexSync.expected;
    if (expected != null && mapped != null) {
      parts.push(`Plex mapped ${mapped}/${expected}`);
    }
  }
  const summary = `${parts.join(", ")}.${result?.note ? ` ${result.note}` : ""}`;
  const details = (result?.errors || []).map((err) => {
    const label = [err?.number, err?.name].filter((part) => part != null && part !== "").join(" · ");
    return `${label || "Channel"}: ${err?.error || "unknown error"}`;
  });
  const plexFailed = result?.plex_sync_failed || plexSync?.ok === false;
  const type = errors > 0 || result?.ok === false || plexFailed ? "error" : "success";
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

/** Engine up + at least one station → maintenance-first UI (not the setup journey). */
function buildCraftFiltersPayload(craft) {
  const genres = Array.isArray(craft?.genres)
    ? craft.genres.filter(Boolean)
    : craft?.genre
      ? [craft.genre]
      : [];
  const decadeRaw = craft?.decade;
  const decade =
    decadeRaw === "" || decadeRaw == null ? undefined : Number(decadeRaw);
  const theme = String(craft?.theme || "").trim();
  const rating = String(craft?.content_rating || "").trim();
  const payload = {};
  if (genres.length) payload.genres = genres;
  if (Number.isFinite(decade)) payload.decade = decade;
  if (theme) payload.themes = [theme];
  if (rating) payload.content_ratings = [rating];
  return payload;
}

function isLiveChannelsLaunched(status, engineProgress) {
  const engineUp = Boolean(
    status?.broadcast?.sidecar_up || engineProgress?.ready || engineProgress?.http_ready,
  );
  return engineUp && Number(status?.channel_count ?? 0) > 0;
}

function LiveStatusCheck({ ok, soft = false, children, testId }) {
  const mark = ok ? "✓" : soft ? "○" : "✗";
  const tone = ok ? "ok" : soft ? "soft" : "fail";
  return (
    <li
      className={`live-channels-check live-channels-check-${tone}`}
      data-testid={testId}
    >
      <span className="live-channels-check-mark" aria-hidden="true">
        {mark}
      </span>
      <span className="live-channels-check-body">{children}</span>
    </li>
  );
}

function LiveReadyBadge({ ready, label = "Ready", testId }) {
  if (!ready) return null;
  return (
    <span className="certified-badge certified-badge-ok" data-testid={testId}>
      ✓ {label}
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
  const [liveCraftOptions, setLiveCraftOptions] = useState(null);
  const [liveCraft, setLiveCraft] = useState({
    name: "",
    number: "",
    source: "motif",
    programming_mode: "shuffle",
    media_scope: "both",
    motif: "",
    cluster_tag: "",
    collection_id: "",
    collection_title: "",
    youth_safe: false,
    genres: [],
    decade: "",
    theme: "",
    content_rating: "",
  });
  const [liveCraftPreview, setLiveCraftPreview] = useState(null);
  const [liveCraftPreviewBusy, setLiveCraftPreviewBusy] = useState(false);
  const [fillerPathDraft, setFillerPathDraft] = useState("");
  const [padFlexDraft, setPadFlexDraft] = useState("");
  const [exclusionNameDraft, setExclusionNameDraft] = useState("");
  const [stationSettingsOpen, setStationSettingsOpen] = useState(null);
  const [liveAttach, setLiveAttach] = useState(null);
  const [liveBusy, setLiveBusy] = useState(null);
  const [liveEngineProgress, setLiveEngineProgress] = useState(null);
  const [liveEngineError, setLiveEngineError] = useState("");
  const [liveContinuityProgress, setLiveContinuityProgress] = useState(null);
  const [livePublishProgress, setLivePublishProgress] = useState(null);
  /** Per-card success/error for Live Channels (not the page-bottom banner). */
  const [liveBlockFeedback, setLiveBlockFeedback] = useState({});
  const [selectedStarters, setSelectedStarters] = useState({});
  const [tunarrLogsOpen, setTunarrLogsOpen] = useState(false);
  const [tunarrLogs, setTunarrLogs] = useState(null);
  const [tunarrLogsBusy, setTunarrLogsBusy] = useState(false);
  const [liveChannelsTab, setLiveChannelsTab] = useState(null); // null = auto by launch state
  const [collectionFilter, setCollectionFilter] = useState("");
  const trackedSyncJobIdRef = useRef(null);
  const syncWasRunningRef = useRef(false);
  const enginePollRef = useRef(null);
  const continuityPollRef = useRef(null);
  const publishPollRef = useRef(null);

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
  const liveLaunched = useMemo(
    () => isLiveChannelsLaunched(liveChannelsStatus, liveEngineProgress),
    [liveChannelsStatus, liveEngineProgress],
  );
  const effectiveLiveTab = liveChannelsTab || (liveLaunched ? "stations" : "setup");
  const filteredLiveCollections = useMemo(() => {
    const rows = liveCraftOptions?.collections || [];
    const scope = liveCraft.media_scope || "both";
    const scopeFiltered =
      scope === "both"
        ? rows
        : rows.filter((row) => {
            const mt = String(row.media_type || "").toLowerCase();
            if (!mt) return true;
            if (scope === "tv") return mt === "show" || mt === "shows" || mt === "tv";
            if (scope === "movies") return mt === "movie" || mt === "movies";
            return true;
          });
    const q = collectionFilter.trim().toLowerCase();
    const filtered = !q
      ? scopeFiltered
      : scopeFiltered.filter((row) => {
          const hay = `${row.title || ""} ${row.label || ""} ${row.source || ""}`.toLowerCase();
          return hay.includes(q);
        });
    // Keep the current selection visible even if it does not match the filter.
    const selectedId = liveCraft.collection_id;
    if (
      selectedId &&
      !filtered.some((row) => row.id === selectedId)
    ) {
      const selected = rows.find((row) => row.id === selectedId);
      if (selected) return [selected, ...filtered];
    }
    return filtered;
  }, [
    liveCraftOptions?.collections,
    collectionFilter,
    liveCraft.collection_id,
    liveCraft.media_scope,
  ]);
  const fillerBinds = settings?.tunarr?.filler_binds || [];

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
    getLiveChannelsCraftOptions()
      .then((opts) => {
        setLiveCraftOptions(opts);
        setLiveCraft((prev) => ({
          ...prev,
          number: prev.number || String(opts.next_channel_number || 100),
          motif: prev.motif || opts.motifs?.[0]?.value || "",
          cluster_tag: prev.cluster_tag || opts.taste_clusters?.[0]?.cluster_tag || "",
          collection_id: prev.collection_id || opts.collections?.[0]?.id || "",
          collection_title: prev.collection_title || opts.collections?.[0]?.title || "",
        }));
        if (opts?.pad_flex_max_minutes != null) {
          setPadFlexDraft((prev) => (prev === "" ? String(opts.pad_flex_max_minutes) : prev));
        }
        if (opts?.exclusion_collection_name) {
          setExclusionNameDraft((prev) => (prev === "" ? opts.exclusion_collection_name : prev));
        }
      })
      .catch(() => setLiveCraftOptions(null));
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
      if (continuityPollRef.current) {
        clearInterval(continuityPollRef.current);
        continuityPollRef.current = null;
      }
      if (publishPollRef.current) {
        clearInterval(publishPollRef.current);
        publishPollRef.current = null;
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

  function setLiveFeedback(block, type, message, options = {}) {
    const key = String(block || "general").trim() || "general";
    const details = Array.isArray(options.details) ? options.details : null;
    setLiveBlockFeedback((prev) => ({
      ...prev,
      [key]: { type, message, details },
    }));
    // Live Channels feedback is inline on the card — never the page-bottom banner.
    setActionAlert((prev) => (prev?.area === "live-channels" ? null : prev));
    setStatus("");
  }

  function clearLiveFeedback(block) {
    if (!block) {
      setLiveBlockFeedback({});
      return;
    }
    setLiveBlockFeedback((prev) => {
      if (!prev[block]) return prev;
      const next = { ...prev };
      delete next[block];
      return next;
    });
  }

  function renderLiveBlockAlert(block) {
    const fb = liveBlockFeedback[block];
    if (!fb?.message) return null;
    return (
      <InlineAlert
        type={fb.type}
        message={fb.message}
        details={fb.details}
        testId={`live-channels-${block}-alert`}
      />
    );
  }

  function setActionFeedback(area, type, message, options = {}) {
    const details = Array.isArray(options.details) ? options.details : null;
    // Live Channels: route to the card block (options.block). Do not park at page bottom.
    if (area === "live-channels") {
      setLiveFeedback(options.block || "general", type, message, { details });
      return;
    }
    setActionAlert({ area, type, message, details });
    // Areas that render their own InlineAlert should not also fill the page footer
    // status line (that produced duplicate red bar + plain text).
    if (area === "tunarr" || options.skipStatus) {
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
    if (area === "live-channels") {
      clearLiveFeedback();
    }
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
        setLiveChannelsTab(null);
        setCollectionFilter("");
        stopEngineProgressPoll();
      }
    } catch (error) {
      updateFeatureFlags({ live_channels_enabled: !enabled });
      setActionFeedback("live-channels", "error", error.message, { block: "hero" });
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

  function stopContinuityProgressPoll() {
    if (continuityPollRef.current) {
      clearInterval(continuityPollRef.current);
      continuityPollRef.current = null;
    }
  }

  async function pollContinuityProgressOnce() {
    try {
      const progress = await getLiveChannelsContinuityStatus();
      setLiveContinuityProgress(progress);
      return progress;
    } catch {
      return null;
    }
  }

  function continuityPhaseLabel(phase) {
    switch (phase) {
      case "queued":
        return "Queued";
      case "remounting":
        return "Remounting Tunarr";
      case "waiting_ready":
        return "Waiting for Tunarr ready";
      case "scoping_libraries":
        return "Scoping libraries";
      case "scanning_filler":
        return "Scanning filler";
      case "attaching":
        return "Attaching continuity";
      case "refilling":
        return "Refilling lineups";
      case "warming":
        return "Warming streams";
      case "done":
        return "Finished";
      case "error":
        return "Failed";
      default:
        return "Working…";
    }
  }

  async function runContinuityJob(body = {}, { successFallback = "Continuity update finished.", block = "stations" } = {}) {
    clearLiveFeedback(block);
    clearActionFeedback("live-channels");
    setLiveBusy("continuity-repair");
    setLiveContinuityProgress({
      phase: "queued",
      percent: 5,
      message: "Starting continuity job…",
      busy: true,
      ok: true,
      determinate: true,
    });
    stopContinuityProgressPoll();
    const startedAt = Date.now();
    const timeoutMs = 12 * 60 * 1000;
    continuityPollRef.current = setInterval(() => {
      pollContinuityProgressOnce().then((progress) => {
        if (!progress) return;
        if (
          progress.phase === "done" ||
          progress.phase === "error" ||
          (!progress.busy && progress.phase !== "queued") ||
          Date.now() - startedAt > timeoutMs
        ) {
          stopContinuityProgressPoll();
        }
      });
    }, 1500);

    try {
      const accepted = await postLiveChannelsContinuityRepair(body);
      if (accepted?.async === false && accepted?.ok != null) {
        // Sync diagnostic path — finish immediately.
        stopContinuityProgressPoll();
        setLiveContinuityProgress({
          phase: accepted.ok ? "done" : "error",
          percent: accepted.ok ? 100 : 0,
          message: accepted.message || successFallback,
          busy: false,
          ok: Boolean(accepted.ok),
          error: accepted.ok ? "" : accepted.message,
          result: accepted,
        });
        setActionFeedback("live-channels",
          accepted.ok ? "success" : "error",
          accepted.message || successFallback,
          { block },
        );
        setLiveChannelsStatus(await getLiveChannelsStatus());
        return accepted;
      }

      const deadline = Date.now() + timeoutMs;
      let progress = await pollContinuityProgressOnce();
      while (Date.now() < deadline) {
        if (progress?.phase === "done" || progress?.phase === "error") break;
        if (progress && !progress.busy && progress.phase !== "queued") break;
        await new Promise((resolve) => setTimeout(resolve, 1500));
        progress = await pollContinuityProgressOnce();
      }
      stopContinuityProgressPoll();
      if (progress?.phase === "done") {
        setActionFeedback("live-channels",
          "success",
          progress.message || progress.result?.message || successFallback,
          { block },
        );
        setLiveChannelsStatus(await getLiveChannelsStatus());
      } else if (progress?.phase === "error") {
        setActionFeedback("live-channels",
          "error",
          progress.error || progress.message || "Continuity repair failed.",
          { block },
        );
      } else {
        setActionFeedback("live-channels",
          "error",
          "Timed out waiting for continuity repair. Check Admin Logs for live_channels.continuity stages.",
          { block },
        );
      }
      return progress;
    } catch (error) {
      stopContinuityProgressPoll();
      setLiveContinuityProgress((prev) => ({
        ...(prev || {}),
        phase: "error",
        percent: 0,
        busy: false,
        ok: false,
        error: error.message,
        message: error.message,
      }));
      setActionFeedback("live-channels", "error", error.message, { block });
      throw error;
    } finally {
      stopContinuityProgressPoll();
      setLiveBusy(null);
    }
  }

  function stopPublishProgressPoll() {
    if (publishPollRef.current) {
      clearInterval(publishPollRef.current);
      publishPollRef.current = null;
    }
  }

  async function pollPublishProgressOnce() {
    try {
      const progress = await getLiveChannelsPublishStatus();
      setLivePublishProgress(progress);
      return progress;
    } catch {
      return null;
    }
  }

  function publishPhaseLabel(phase) {
    switch (phase) {
      case "queued":
        return "Queued";
      case "wiring":
        return "Wiring media source";
      case "matching":
        return "Matching titles";
      case "publishing":
        return "Publishing station";
      case "plex_sync":
        return "Refreshing Plex channels";
      case "warming":
        return "Warming streams";
      case "done":
        return "Finished";
      case "error":
        return "Failed";
      default:
        return "Working…";
    }
  }

  async function runPublishJob(startFn, { busyKey = "publish", block = "collection", successFallback = "Publish finished." } = {}) {
    clearLiveFeedback(block);
    clearActionFeedback("live-channels");
    setLiveBusy(busyKey);
    setLivePublishProgress({
      phase: "queued",
      percent: 5,
      message: "Starting publish…",
      busy: true,
      ok: true,
      determinate: true,
    });
    stopPublishProgressPoll();
    const startedAt = Date.now();
    const timeoutMs = 12 * 60 * 1000;
    publishPollRef.current = setInterval(() => {
      pollPublishProgressOnce().then((progress) => {
        if (!progress) return;
        if (
          progress.phase === "done" ||
          progress.phase === "error" ||
          (!progress.busy && progress.phase !== "queued") ||
          Date.now() - startedAt > timeoutMs
        ) {
          stopPublishProgressPoll();
        }
      });
    }, 1500);

    try {
      const accepted = await startFn();
      if (accepted?.async === false && accepted?.ok != null) {
        stopPublishProgressPoll();
        const feedback = formatPublishFeedback(accepted);
        setLivePublishProgress({
          phase: accepted.ok !== false && !accepted.count_errors ? "done" : "error",
          percent: 100,
          message: feedback.summary,
          busy: false,
          ok: feedback.type !== "error",
          error: feedback.type === "error" ? feedback.summary : "",
          result: accepted,
        });
        setActionFeedback("live-channels", feedback.type, feedback.summary, {
          block,
          details: feedback.details,
        });
        setLiveChannelsStatus(await getLiveChannelsStatus());
        setLiveCraftOptions(await getLiveChannelsCraftOptions());
        return accepted;
      }

      const deadline = Date.now() + timeoutMs;
      let progress = await pollPublishProgressOnce();
      while (Date.now() < deadline) {
        if (progress?.phase === "done" || progress?.phase === "error") break;
        if (progress && !progress.busy && progress.phase !== "queued") break;
        await new Promise((resolve) => setTimeout(resolve, 1500));
        progress = await pollPublishProgressOnce();
      }
      stopPublishProgressPoll();
      if (progress?.phase === "done") {
        const result = progress.result || {};
        const feedback = formatPublishFeedback({
          ...result,
          note: progress.message || result.note,
          ok: true,
        });
        setActionFeedback("live-channels", "success", feedback.summary, {
          block,
          details: feedback.details,
        });
        setLiveChannelsStatus(await getLiveChannelsStatus());
        setLiveCraftOptions(await getLiveChannelsCraftOptions());
      } else if (progress?.phase === "error") {
        setActionFeedback("live-channels", "error", progress.error || progress.message || "Publish failed.", {
          block,
        });
      } else {
        setActionFeedback("live-channels", "error", "Timed out waiting for publish. Check Admin Logs for live_channels.publish stages.", {
          block,
        });
      }
      return progress;
    } catch (error) {
      stopPublishProgressPoll();
      setLivePublishProgress((prev) => ({
        ...(prev || {}),
        phase: "error",
        percent: 0,
        busy: false,
        ok: false,
        error: error.message,
        message: error.message,
      }));
      setActionFeedback("live-channels", "error", error.message, { block });
      throw error;
    } finally {
      stopPublishProgressPoll();
      setLiveBusy(null);
    }
  }

  function renderPublishProgress(block) {
    const busyMatch =
      (block === "collection" && liveBusy === "collection") ||
      (block === "craft" && liveBusy === "craft") ||
      (block === "publish" && (liveBusy === "collection" || liveBusy === "craft"));
    if (
      !(
        busyMatch ||
        (livePublishProgress &&
          livePublishProgress.phase &&
          livePublishProgress.phase !== "idle" &&
          (liveBusy === "collection" || liveBusy === "craft" || livePublishProgress.mode === block))
      )
    ) {
      return null;
    }
    const done = livePublishProgress?.phase === "done";
    const failed = livePublishProgress?.phase === "error";
    return (
      <div
        className="live-channels-engine-progress"
        data-testid={`live-channels-publish-progress-${block}`}
      >
        {done ? (
          <InlineAlert
            type="success"
            message={livePublishProgress?.message || "Publish finished"}
            testId={`live-channels-publish-success-${block}`}
          />
        ) : (
          <>
            <p className="live-channels-engine-progress-headline">
              {livePublishProgress?.message || "Publishing…"}
            </p>
            <div
              className="live-channels-engine-progress-bar"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={
                Number.isFinite(livePublishProgress?.percent)
                  ? livePublishProgress.percent
                  : undefined
              }
              aria-label="Publish progress"
            >
              <span
                className="live-channels-engine-progress-fill"
                style={{
                  width: `${Math.max(
                    8,
                    Math.min(100, Number(livePublishProgress?.percent) || 15),
                  )}%`,
                }}
              />
            </div>
            <p className="wizard-note live-channels-engine-phase">
              {publishPhaseLabel(livePublishProgress?.phase)}
              {Number.isFinite(livePublishProgress?.percent)
                ? ` · ${livePublishProgress.percent}%`
                : ""}
            </p>
          </>
        )}
        {failed ? (
          <div
            className="inline-alert inline-alert-error"
            data-testid={`live-channels-publish-error-${block}`}
            role="alert"
          >
            <span className="inline-alert-message">
              {livePublishProgress?.error || livePublishProgress?.message}
            </span>
          </div>
        ) : null}
      </div>
    );
  }

  function renderContinuityProgress() {
    if (
      !(
        liveBusy === "continuity-repair" ||
        (liveContinuityProgress &&
          liveContinuityProgress.phase &&
          liveContinuityProgress.phase !== "idle")
      )
    ) {
      return null;
    }
    const done = liveContinuityProgress?.phase === "done";
    const failed = liveContinuityProgress?.phase === "error";
    return (
      <div
        className="live-channels-engine-progress"
        data-testid="live-channels-continuity-progress"
      >
        {done ? (
          <InlineAlert
            type="success"
            message={liveContinuityProgress?.message || "Continuity repair finished"}
            testId="live-channels-continuity-success"
          />
        ) : (
          <>
            <p className="live-channels-engine-progress-headline">
              {liveContinuityProgress?.message ||
                (liveBusy === "continuity-repair" ? "Repairing continuity…" : "Working…")}
            </p>
            <div
              className={`live-channels-engine-progress-bar${
                liveBusy === "continuity-repair" && !(liveContinuityProgress?.percent > 0)
                  ? " is-indeterminate"
                  : ""
              }`}
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={
                Number.isFinite(liveContinuityProgress?.percent)
                  ? liveContinuityProgress.percent
                  : undefined
              }
              aria-label="Continuity repair progress"
            >
              <span
                className="live-channels-engine-progress-fill"
                style={{
                  width: `${Math.max(
                    8,
                    Math.min(100, Number(liveContinuityProgress?.percent) || 15),
                  )}%`,
                }}
              />
            </div>
            <p className="wizard-note live-channels-engine-phase">
              {continuityPhaseLabel(liveContinuityProgress?.phase)}
              {Number.isFinite(liveContinuityProgress?.percent)
                ? ` · ${liveContinuityProgress.percent}%`
                : ""}
            </p>
          </>
        )}
        {failed ? (
          <div
            className="inline-alert inline-alert-error"
            data-testid="live-channels-continuity-error"
            role="alert"
          >
            <span className="inline-alert-message">
              {liveContinuityProgress?.error || liveContinuityProgress?.message}
            </span>
          </div>
        ) : null}
      </div>
    );
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
        setActionFeedback("live-channels", "error", message, { block: "engine" });
        stopEngineProgressPoll();
        setLiveBusy(null);
        return;
      }
      // Keep polling until Tunarr HTTP is ready (log banner alone is not enough), up to ~5 min.
      const deadline = Date.now() + timeoutMs;
      let progress = await pollEngineProgressOnce();
      while (Date.now() < deadline) {
        if (progress?.ready && progress?.http_ready) break;
        if (progress?.ready) break;
        if (progress?.phase === "error") break;
        await new Promise((resolve) => setTimeout(resolve, 1500));
        progress = await pollEngineProgressOnce();
      }
      stopEngineProgressPoll();
      if (progress?.ready) {
        setActionFeedback("live-channels",
          "success",
          progress.message || "Tunarr is ready!",
          { block: "engine" },
        );
      } else if (progress?.phase === "error") {
        setLiveEngineError(progress.error || progress.message || "Broadcast engine failed.");
        setActionFeedback("live-channels", "error", progress.error || progress.message, { block: "engine" });
      } else {
        const stillStarting = Boolean(progress?.still_starting || progress?.container_running);
        const timeoutMsg = stillStarting
          ? "Tunarr is still starting — HTTP not ready yet. Meili/scan noise during boot is normal; try again shortly."
          : "Timed out waiting for Tunarr to become ready. Check Broadcast engine logs below.";
        // stillStarting: container up, HTTP not ready — soft notice (ok:true), not a failure.
        setLiveEngineError(stillStarting ? "" : timeoutMsg);
        setLiveEngineProgress((prev) => ({
          ...(prev || {}),
          phase: stillStarting ? "waiting_ready" : "error",
          percent: prev?.percent || 80,
          message: timeoutMsg,
          ready: false,
          busy: false,
          ok: stillStarting,
          error: stillStarting ? "" : timeoutMsg,
          still_starting: stillStarting,
        }));
        setActionFeedback(
          "live-channels",
          liveChannelsStartTimeoutAlertType(stillStarting),
          timeoutMsg,
          { block: "engine" },
        );
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
      setActionFeedback("live-channels", "error", message, { block: "engine" });
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
                {renderLiveBlockAlert("hero")}
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
                    <h2>{liveLaunched ? "Stations on the air" : "Live Channels is on"}</h2>
                    <p className="live-channels-hero-lede">
                      {liveLaunched
                        ? "Craft, refill, and watch system health here. Setup and Docker details live under Installation."
                        : "Finish the steps below to add Tunarr beside any existing OTA tuner in Plex Live TV. Watching stays in Plex — nothing replaces your antenna DVR."}
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
                {renderLiveBlockAlert("hero")}

                {liveLaunched ? (
                  <div
                    className="live-channels-tabs"
                    role="tablist"
                    aria-label="Live Channels sections"
                    data-testid="live-channels-tabs"
                  >
                    <button
                      type="button"
                      role="tab"
                      aria-selected={effectiveLiveTab === "stations"}
                      className={
                        effectiveLiveTab === "stations"
                          ? "live-channels-tab is-active"
                          : "live-channels-tab"
                      }
                      data-testid="live-channels-tab-stations"
                      onClick={() => setLiveChannelsTab("stations")}
                    >
                      Stations
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={effectiveLiveTab === "setup"}
                      className={
                        effectiveLiveTab === "setup"
                          ? "live-channels-tab is-active"
                          : "live-channels-tab"
                      }
                      data-testid="live-channels-tab-installation"
                      onClick={() => setLiveChannelsTab("setup")}
                    >
                      Installation
                    </button>
                  </div>
                ) : null}

                <div
                  className="live-channels-journey"
                  data-live-mode={liveLaunched ? "maintenance" : "setup"}
                >
                  {!liveLaunched || effectiveLiveTab === "stations" ? (
                  <div
                    className={`service-card${
                      liveChannelsStatus?.broadcast?.sidecar_up ? " service-ok" : ""
                    }`}
                    data-testid="live-channels-health-strip"
                  >
                    <div className="service-card-header">
                      <div className="service-card-title">
                        <h3>What's on the air</h3>
                        <LiveReadyBadge
                          ready={Boolean(liveChannelsStatus?.broadcast?.sidecar_up)}
                          label="Broadcast healthy"
                          testId="live-channels-health-ready"
                        />
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
                            .catch((error) => setActionFeedback("live-channels", "error", error.message, { block: "health" }))
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
                            liveChannelsStatus.guide_index?.lineup
                              ? `${liveChannelsStatus.guide_index.lineup.filled_count ?? 0} with lineups` +
                                (liveChannelsStatus.guide_index.lineup.empty_count
                                  ? ` · ${liveChannelsStatus.guide_index.lineup.empty_count} empty`
                                  : "")
                              : null,
                            liveChannelsStatus.guide_index?.xmltv?.ok
                              ? `${liveChannelsStatus.guide_index.xmltv.content_programme_count ?? 0} guide titles in XMLTV`
                              : null,
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
                    {renderLiveBlockAlert("health")}
                    {liveChannelsStatus?.guide_index ? (
                      <div
                        className="wizard-note"
                        data-testid="live-channels-guide-index"
                      >
                        <p>
                          <strong>Guide / indexing</strong>
                          {" — "}
                          {liveChannelsStatus.guide_index.owner_hint ||
                            "Refresh after publish or attach."}
                        </p>
                        <ul data-testid="live-channels-guide-index-list">
                          <li>
                            Tunarr libraries enabled:{" "}
                            {liveChannelsStatus.guide_index.media_libraries?.enabled_count ?? 0}
                            {liveChannelsStatus.guide_index.media_libraries?.scanning_count
                              ? ` · scanning ${liveChannelsStatus.guide_index.media_libraries.scanning_count}`
                              : ""}
                          </li>
                          <li>
                            Lineups playable:{" "}
                            {liveChannelsStatus.guide_index.lineup?.playable ? "yes" : "no"}
                            {liveChannelsStatus.guide_index.lineup?.empty_count
                              ? ` (${liveChannelsStatus.guide_index.lineup.empty_count} empty)`
                              : ""}
                          </li>
                          <li>
                            XMLTV programmes:{" "}
                            {liveChannelsStatus.guide_index.xmltv?.programme_count ?? 0}
                            {" · "}
                            titled content:{" "}
                            {liveChannelsStatus.guide_index.xmltv?.content_programme_count ?? 0}
                          </li>
                          <li>
                            Last Plex guide attach:{" "}
                            {liveChannelsStatus.guide_index.last_attach?.at
                              ? `${liveChannelsStatus.guide_index.last_attach.ok ? "ok" : "failed"} · ${liveChannelsStatus.guide_index.last_attach.at}${
                                  liveChannelsStatus.guide_index.last_attach.dvr_key
                                    ? ` · DVR ${liveChannelsStatus.guide_index.last_attach.dvr_key}`
                                    : ""
                                }`
                              : "not run yet — use Attach Tunarr guide in Plex below"}
                          </li>
                          <li data-testid="live-channels-plex-mapped">
                            Plex Tunarr map:{" "}
                            {liveChannelsStatus.guide_index.plex_livetv?.expected != null
                              ? `${liveChannelsStatus.guide_index.plex_livetv?.mapped ?? 0}/${liveChannelsStatus.guide_index.plex_livetv.expected}`
                              : "—"}
                            {liveChannelsStatus.guide_index.plex_livetv?.device_present
                              ? ` · device ${liveChannelsStatus.guide_index.plex_livetv.device_status || "present"}`
                              : " · device missing"}
                            {liveChannelsStatus.guide_index.plex_livetv?.hdhr_ok === false
                              ? " · Tunarr HDHR unreachable"
                              : ""}
                            {liveChannelsStatus.guide_index.plex_livetv?.mapping_message
                              ? ` — ${liveChannelsStatus.guide_index.plex_livetv.mapping_message}`
                              : ""}
                          </li>
                          {liveChannelsStatus.icon_probe ? (
                            <li data-testid="live-channels-icon-probe">
                              Channel icon probe:{" "}
                              {liveChannelsStatus.icon_probe.ok
                                ? `ok · ${liveChannelsStatus.icon_probe.url || ""}`
                                : liveChannelsStatus.icon_probe.message || "unreachable"}
                            </li>
                          ) : null}
                        </ul>
                      </div>
                    ) : null}
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
                  ) : null}

                  {!liveLaunched || effectiveLiveTab === "setup" ? (
                  <>
                  <div
                    className={`service-card ${
                      testResults.tunarr?.state === "success" ||
                      liveChannelsStatus?.broadcast?.sidecar_up ||
                      liveEngineProgress?.ready
                        ? "service-ok"
                        : ""
                    } ${testing === "tunarr" ? "service-loading" : ""} ${testResults.tunarr?.state === "error" ? "service-error" : ""}`}
                  >
                    <div className="service-card-header">
                      <div className="service-card-title">
                        {!liveLaunched ? (
                          <p className="live-channels-step-label">Connection</p>
                        ) : null}
                        <h3>Broadcast engine connection</h3>
                        <CertifiedBadge
                          certified={
                            certifications.tunarr?.certified ||
                            testResults.tunarr?.state === "success" ||
                            liveChannelsStatus?.broadcast?.sidecar_up
                          }
                          testing={testing === "tunarr"}
                          serviceId="tunarr"
                        />
                        <LiveReadyBadge
                          ready={Boolean(
                            liveEngineProgress?.ready || liveChannelsStatus?.broadcast?.sidecar_up,
                          )}
                          label="Engine ready"
                          testId="live-channels-engine-ready-badge"
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
                            }).catch((error) => setActionFeedback("live-channels", "error", error.message, { block: "connection" }))
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
                                setActionFeedback("live-channels", "error", error.message, { block: "connection" }),
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
                              setActionFeedback("live-channels", "error", error.message, { block: "connection" }),
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
                    {renderLiveBlockAlert("connection")}
                  </div>

                  <div
                    className={`service-card${livePreflight?.ready ? " service-ok" : ""}`}
                    data-testid="live-channels-preflight"
                  >
                    <div className="service-card-header">
                      <div className="service-card-title">
                        {!liveLaunched ? (
                          <p className="live-channels-step-label">Step 1</p>
                        ) : null}
                        <h3>Check you're ready</h3>
                        <LiveReadyBadge
                          ready={Boolean(livePreflight?.ready)}
                          label="Ready"
                          testId="live-channels-preflight-ready"
                        />
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
                            setActionFeedback("live-channels",
                              result.ready ? "success" : "error",
                              result.summary || "Ready check finished.", { block: "preflight",  details: hardFails },
                            );
                          } catch (error) {
                            setActionFeedback("live-channels", "error", error.message, { block: "preflight" });
                          } finally {
                            setLiveBusy(null);
                          }
                        }}
                      >
                        {liveBusy === "preflight" ? "Checking…" : "Run ready check"}
                      </button>
                    </div>
                    {renderLiveBlockAlert("preflight")}
                    <label className="config-toggle" data-testid="live-channels-plex-pass-confirm">
                      <input
                        type="checkbox"
                        checked={Boolean(settings?.tunarr?.plex_pass_confirmed)}
                        onChange={(event) => {
                          const confirmed = event.target.checked;
                          updateTunarrSettings({ plex_pass_confirmed: confirmed });
                          persistSettings({
                            tunarr: { ...(settings.tunarr || {}), plex_pass_confirmed: confirmed },
                          }).catch((error) => setActionFeedback("live-channels", "error", error.message, { block: "preflight" }));
                        }}
                      />
                      <span>
                        I have an active Plex Pass (needed for Live TV / DVR). Projectionist can't check this
                        for you.
                      </span>
                    </label>
                    {livePreflight?.checks?.length ? (
                      <ul className="live-channels-check-list" data-testid="live-channels-preflight-list">
                        {livePreflight.checks.map((check) => (
                          <LiveStatusCheck key={check.id} ok={check.ok} soft={check.soft}>
                            {check.label}: {check.message}
                          </LiveStatusCheck>
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
                    <div
                      className={`service-card${liveEngineProgress?.ready ? " service-ok" : ""}`}
                      data-testid="live-channels-lifecycle"
                    >
                      <div className="service-card-header">
                        <div className="service-card-title">
                          {!liveLaunched ? (
                            <p className="live-channels-step-label">Step 2</p>
                          ) : null}
                          <h3>Start the broadcast engine</h3>
                          <LiveReadyBadge
                            ready={Boolean(liveEngineProgress?.ready)}
                            label="Tunarr is ready"
                            testId="live-channels-engine-ready"
                          />
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
                              className="live-channels-check-list"
                              data-testid="live-channels-engine-ready-list"
                            >
                              <LiveStatusCheck ok>Broadcast engine: Tunarr is ready</LiveStatusCheck>
                              {liveEngineProgress.http_ready ? (
                                <LiveStatusCheck ok>API health: responding</LiveStatusCheck>
                              ) : (
                                <LiveStatusCheck soft>API health: waiting</LiveStatusCheck>
                              )}
                              {liveEngineProgress.logs_ready ? (
                                <LiveStatusCheck ok>Startup log: “Tunarr is ready!”</LiveStatusCheck>
                              ) : (
                                <LiveStatusCheck soft>Startup log: waiting</LiveStatusCheck>
                              )}
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
                      {renderLiveBlockAlert("engine")}
                    </div>
                  ) : null}

                  <div
                    className={`service-card${
                      liveChannelsStatus?.continuity?.ok ? " service-ok" : ""
                    }`}
                    data-testid="live-channels-filler-paths"
                  >
                    <div className="service-card-header">
                      <div className="service-card-title">
                        <h3>Filler programming paths</h3>
                        <LiveReadyBadge
                          ready={Boolean(liveChannelsStatus?.continuity?.ok)}
                          label="Continuity ready"
                          testId="live-channels-continuity-ready"
                        />
                      </div>
                      <button
                        type="button"
                        className="ghost"
                        data-testid="live-channels-rescan-filler"
                        disabled={liveBusy === "continuity-repair"}
                        onClick={async () => {
                          if (
                            !window.confirm(
                              "Rescan filler and repair continuity? This remounts filler paths if needed, force-scans the local filler library, attaches the shared list, and warms streams. Active Live TV sessions may briefly drop while Tunarr restarts.",
                            )
                          ) {
                            return;
                          }
                          try {
                            await runContinuityJob(
                              {
                                rescan: true,
                                repair: true,
                                refill_lineups: true,
                              },
                              { successFallback: "Filler rescan finished.", block: "filler" },
                            );
                          } catch {
                            /* feedback already set */
                          }
                        }}
                      >
                        {liveBusy === "continuity-repair" ? "Working…" : "Rescan filler"}
                      </button>
                    </div>
                    <p className="wizard-note">
                      Commercial-cut shows often need up to 15 minutes of filler between episodes.
                      Add one or more host folders of bumpers / trailers / shorts — Projectionist
                      mounts each path into Tunarr and builds one randomized continuity list for
                      every station. Empty or thin pools show as continuity degraded rather than green.
                    </p>
                    {!liveLaunched || effectiveLiveTab === "setup"
                      ? renderContinuityProgress()
                      : null}
                    {renderLiveBlockAlert("filler")}
                    <ul
                      className="live-channels-check-list"
                      data-testid="live-channels-continuity-checks"
                    >
                      {(liveChannelsStatus?.continuity?.checks || []).map((check) => (
                        <LiveStatusCheck
                          key={check.id}
                          ok={check.ok}
                          soft={check.soft}
                          testId={`live-channels-install-continuity-${check.id}`}
                        >
                          {check.label}: {check.message}
                        </LiveStatusCheck>
                      ))}
                    </ul>
                    <div className="service-fields" data-testid="live-channels-filler-editor">
                      {(fillerBinds || []).map((bind, index) => (
                        <div
                          key={`${bind}-${index}`}
                          className="live-channels-filler-row"
                          data-testid={`live-channels-filler-row-${index}`}
                        >
                          <code>{bind}</code>
                          <button
                            type="button"
                            className="ghost"
                            data-testid={`live-channels-filler-remove-${index}`}
                            onClick={() => {
                              const next = fillerBinds.filter((_, i) => i !== index);
                              updateTunarrSettings({ filler_binds: next });
                              persistSettings({
                                tunarr: { ...(settings.tunarr || {}), filler_binds: next },
                              }).catch((error) =>
                                setActionFeedback("live-channels", "error", error.message, { block: "filler" }),
                              );
                            }}
                          >
                            Remove
                          </button>
                        </div>
                      ))}
                      <label>
                        Add host folder
                        <input
                          type="text"
                          data-testid="live-channels-filler-path-input"
                          placeholder="/mnt/user/media/bumpers"
                          value={fillerPathDraft}
                          onChange={(event) => setFillerPathDraft(event.target.value)}
                        />
                      </label>
                      <button
                        type="button"
                        data-testid="live-channels-filler-add"
                        disabled={!fillerPathDraft.trim()}
                        onClick={() => {
                          const path = fillerPathDraft.trim();
                          if (!path) return;
                          const next = [...fillerBinds, path];
                          updateTunarrSettings({ filler_binds: next });
                          setFillerPathDraft("");
                          persistSettings({
                            tunarr: { ...(settings.tunarr || {}), filler_binds: next },
                          })
                            .then(() =>
                              setActionFeedback("live-channels",
                                "success",
                                "Filler path saved. Restart the broadcast engine if it is already running so Tunarr picks up the new mount, then Rescan filler.",
                              { block: "filler" },
                              ),
                            )
                            .catch((error) =>
                              setActionFeedback("live-channels", "error", error.message, { block: "filler" }),
                            );
                        }}
                      >
                        Add path
                      </button>
                    </div>
                  </div>

                  <div className="service-card" data-testid="live-channels-schedule-settings">
                    <div className="service-card-header">
                      <div className="service-card-title">
                        <h3>Schedule pad &amp; exclusion</h3>
                      </div>
                    </div>
                    <p className="wizard-note">
                      Pad flex caps commercial-cut gaps toward :00/:30 (0 = back-to-back). Exclusion
                      skips a named Plex collection (default NoLive) during recipe fill and starters.
                      After library sync, stations with stored recipes refill automatically when enabled.
                    </p>
                    <div className="service-fields">
                      <label>
                        Pad flex max (minutes)
                        <input
                          type="number"
                          min={0}
                          max={30}
                          data-testid="live-channels-pad-flex"
                          value={padFlexDraft}
                          placeholder={String(
                            liveCraftOptions?.pad_flex_max_minutes ??
                              settings?.tunarr?.pad_flex_max_minutes ??
                              15,
                          )}
                          onChange={(event) => setPadFlexDraft(event.target.value)}
                        />
                      </label>
                      <label>
                        Exclusion collection name
                        <input
                          type="text"
                          data-testid="live-channels-exclusion-name"
                          value={exclusionNameDraft}
                          placeholder="NoLive"
                          onChange={(event) => setExclusionNameDraft(event.target.value)}
                        />
                      </label>
                    </div>
                    <div className="wizard-actions">
                      <button
                        type="button"
                        className="ghost"
                        data-testid="live-channels-save-schedule-settings"
                        disabled={liveBusy === "engine-settings"}
                        onClick={async () => {
                          setLiveBusy("engine-settings");
                          try {
                            const minutes = Number(padFlexDraft);
                            const result = await patchLiveChannelsEngineSettings({
                              pad_flex_max_minutes: Number.isFinite(minutes) ? minutes : 15,
                              exclusion_collection_name: exclusionNameDraft || "NoLive",
                              auto_refresh_stations_after_sync: true,
                            });
                            setPadFlexDraft(String(result.pad_flex_max_minutes ?? minutes));
                            setExclusionNameDraft(
                              result.exclusion_collection_name || exclusionNameDraft || "NoLive",
                            );
                            updateTunarrSettings({
                              pad_flex_max_minutes: result.pad_flex_max_minutes,
                              exclusion_collection_name: result.exclusion_collection_name,
                              auto_refresh_stations_after_sync:
                                result.auto_refresh_stations_after_sync,
                            });
                            setActionFeedback(
                              "live-channels",
                              "success",
                              `Saved pad ${result.pad_flex_max_minutes}m · exclusion “${result.exclusion_collection_name}”.`,
                              { block: "filler" },
                            );
                          } catch (error) {
                            setActionFeedback("live-channels", "error", error.message, {
                              block: "filler",
                            });
                          } finally {
                            setLiveBusy(null);
                          }
                        }}
                      >
                        {liveBusy === "engine-settings" ? "Saving…" : "Save pad & exclusion"}
                      </button>
                    </div>
                  </div>

                  </>
                  ) : null}

                  {!liveLaunched || effectiveLiveTab === "stations" ? (
                  <>
                  <div className="service-card" data-testid="live-channels-starters">
                    <div className="service-card-header">
                      <div className="service-card-title">
                        {!liveLaunched ? (
                          <p className="live-channels-step-label">
                            Step {settings?.tunarr?.docker_orchestration ? "3" : "2"}
                          </p>
                        ) : null}
                        <h3>Create / publish channels</h3>
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
                            setActionFeedback("live-channels", "error", error.message, { block: "connection" });
                          } finally {
                            setLiveBusy(null);
                          }
                        }}
                      >
                        {liveBusy === "starters" ? "Loading…" : "Propose starters"}
                      </button>
                    </div>
                    <p className="wizard-note">
                      Three ways to add stations — none require Tunarr’s own UI. Publish enables
                      Tunarr’s Plex libraries, fills lineups with real titles, and skips numbers that
                      already exist (re-publish / Refill refreshes empty lineups).
                    </p>
                    {renderLiveBlockAlert("starters")}

                    <div className="live-channels-craft-block" data-testid="live-channels-craft">
                      <h4>Craft a custom station</h4>
                      <p className="wizard-note">
                        {liveCraftOptions?.hint ||
                          "Name the station, pick a motif / taste cluster / collection / Chaos, then publish to the tuner."}
                      </p>
                      <div className="service-fields live-channels-craft-fields">
                        <label>
                          Station name
                          <input
                            type="text"
                            data-testid="live-channels-craft-name"
                            value={liveCraft.name}
                            placeholder="e.g. Midnight Mystery"
                            onChange={(event) =>
                              setLiveCraft((prev) => ({ ...prev, name: event.target.value }))
                            }
                          />
                        </label>
                        <label>
                          Channel number
                          <input
                            type="number"
                            min={1}
                            data-testid="live-channels-craft-number"
                            value={liveCraft.number}
                            onChange={(event) =>
                              setLiveCraft((prev) => ({ ...prev, number: event.target.value }))
                            }
                          />
                        </label>
                        <label>
                          Recipe
                          <select
                            data-testid="live-channels-craft-source"
                            value={liveCraft.source}
                            onChange={(event) => {
                              const source = event.target.value;
                              setLiveCraft((prev) => ({
                                ...prev,
                                source,
                                programming_mode:
                                  source === "collection"
                                    ? "sequential"
                                    : source === "chaos"
                                      ? "chaos"
                                      : "shuffle",
                                youth_safe: source === "youth",
                              }));
                            }}
                          >
                            {(liveCraftOptions?.sources || [
                              { id: "motif", label: "Plot motif" },
                              { id: "taste_cluster", label: "Taste cluster" },
                              { id: "collection", label: "Collection / list" },
                              { id: "chaos", label: "Chaos" },
                              { id: "youth", label: "Youth-safe" },
                            ]).map((src) => (
                              <option key={src.id} value={src.id}>
                                {src.label}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Programming
                          <select
                            data-testid="live-channels-craft-mode"
                            value={liveCraft.programming_mode}
                            onChange={(event) =>
                              setLiveCraft((prev) => ({
                                ...prev,
                                programming_mode: event.target.value,
                              }))
                            }
                          >
                            {(liveCraftOptions?.programming_modes || [
                              { id: "shuffle", label: "Shuffle" },
                              { id: "sequential", label: "Sequential" },
                              { id: "chaos", label: "Chaos" },
                            ]).map((mode) => (
                              <option key={mode.id} value={mode.id}>
                                {mode.label}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Media
                          <select
                            data-testid="live-channels-craft-media-scope"
                            value={liveCraft.media_scope || "both"}
                            onChange={(event) =>
                              setLiveCraft((prev) => ({
                                ...prev,
                                media_scope: event.target.value,
                                collection_id: "",
                                collection_title: "",
                              }))
                            }
                          >
                            {(liveCraftOptions?.media_scopes || [
                              { id: "tv", label: "TV" },
                              { id: "movies", label: "Movies" },
                              { id: "both", label: "Both" },
                            ]).map((scope) => (
                              <option key={scope.id} value={scope.id}>
                                {scope.label}
                              </option>
                            ))}
                          </select>
                        </label>
                        {liveCraft.source === "motif" ? (
                          <label>
                            Motif
                            <select
                              data-testid="live-channels-craft-motif"
                              value={liveCraft.motif}
                              onChange={(event) =>
                                setLiveCraft((prev) => ({
                                  ...prev,
                                  motif: event.target.value,
                                  name: prev.name || event.target.value,
                                }))
                              }
                            >
                              <option value="">Select a motif…</option>
                              {(liveCraftOptions?.motifs || []).map((motif) => (
                                <option key={motif.value} value={motif.value}>
                                  {motif.label}
                                  {motif.count ? ` (${motif.count})` : ""}
                                </option>
                              ))}
                            </select>
                          </label>
                        ) : null}
                        {liveCraft.source === "taste_cluster" ? (
                          <label>
                            Taste cluster
                            <select
                              data-testid="live-channels-craft-cluster"
                              value={liveCraft.cluster_tag}
                              onChange={(event) =>
                                setLiveCraft((prev) => ({
                                  ...prev,
                                  cluster_tag: event.target.value,
                                  name: prev.name || event.target.value,
                                }))
                              }
                            >
                              <option value="">Select a cluster…</option>
                              {(liveCraftOptions?.taste_clusters || []).map((cluster) => (
                                <option key={cluster.cluster_tag} value={cluster.cluster_tag}>
                                  {cluster.label}
                                </option>
                              ))}
                            </select>
                          </label>
                        ) : null}
                        {liveCraft.source === "collection" ? (
                          <label className="live-channels-craft-collection">
                            Collection
                            <input
                              type="search"
                              className="live-channels-collection-filter"
                              data-testid="live-channels-craft-collection-filter"
                              placeholder="Search collections…"
                              value={collectionFilter}
                              onChange={(event) => setCollectionFilter(event.target.value)}
                              autoComplete="off"
                            />
                            <select
                              data-testid="live-channels-craft-collection"
                              className="live-channels-collection-select"
                              value={liveCraft.collection_id}
                              onChange={(event) => {
                                const id = event.target.value;
                                const match = (liveCraftOptions?.collections || []).find(
                                  (row) => row.id === id,
                                );
                                setLiveCraft((prev) => ({
                                  ...prev,
                                  collection_id: id,
                                  collection_title: match?.title || "",
                                  name: prev.name || match?.title || "",
                                }));
                              }}
                            >
                              <option value="">Select a collection…</option>
                              {filteredLiveCollections.map((row) => (
                                <option key={row.id || row.title} value={row.id} title={row.label}>
                                  {row.label}
                                  {row.source === "plex" ? " · Plex" : ""}
                                  {row.source === "published" ? " · Published" : ""}
                                  {row.item_count ? ` (${row.item_count})` : ""}
                                </option>
                              ))}
                            </select>
                            {!(liveCraftOptions?.collections || []).length ? (
                              <p
                                className="wizard-note"
                                data-testid="live-channels-craft-collections-empty"
                              >
                                {liveCraftOptions?.collections_empty_hint ||
                                  liveCraftOptions?.collections_error ||
                                  "No collections loaded. Create one in Plex, or publish a Projectionist list."}
                              </p>
                            ) : (
                              <p
                                className="wizard-note live-channels-collection-count"
                                data-testid="live-channels-craft-collections-count"
                              >
                                {collectionFilter.trim()
                                  ? `${filteredLiveCollections.length} match${
                                      filteredLiveCollections.length === 1 ? "" : "es"
                                    } of ${liveCraftOptions.collections_total} collections`
                                  : `${liveCraftOptions.collections_total} collection${
                                      liveCraftOptions.collections_total === 1 ? "" : "s"
                                    } available`}
                              </p>
                            )}
                          </label>
                        ) : null}
                        <div
                          className="live-channels-craft-filters"
                          data-testid="live-channels-craft-filters"
                        >
                          <p className="wizard-note">
                            Additive filters (AND) — e.g. 1970s ∩ Action ∩ martial-arts theme ∩ Movies.
                            Titles in the “{liveCraftOptions?.exclusion_collection_name || "NoLive"}”
                            Plex collection are skipped.
                          </p>
                          <label>
                            Genre
                            <select
                              data-testid="live-channels-craft-genre"
                              value={liveCraft.genres?.[0] || ""}
                              onChange={(event) =>
                                setLiveCraft((prev) => ({
                                  ...prev,
                                  genres: event.target.value ? [event.target.value] : [],
                                }))
                              }
                            >
                              <option value="">Any genre</option>
                              {(liveCraftOptions?.filter_options?.genres || []).map((row) => (
                                <option key={row.value} value={row.value}>
                                  {row.label}
                                  {row.count ? ` (${row.count})` : ""}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label>
                            Decade
                            <select
                              data-testid="live-channels-craft-decade"
                              value={liveCraft.decade === "" || liveCraft.decade == null ? "" : String(liveCraft.decade)}
                              onChange={(event) =>
                                setLiveCraft((prev) => ({
                                  ...prev,
                                  decade: event.target.value,
                                }))
                              }
                            >
                              <option value="">Any decade</option>
                              {(liveCraftOptions?.filter_options?.decades || []).map((row) => (
                                <option key={row.value} value={String(row.value)}>
                                  {row.label}
                                  {row.count ? ` (${row.count})` : ""}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label>
                            Theme
                            <select
                              data-testid="live-channels-craft-theme"
                              value={liveCraft.theme || ""}
                              onChange={(event) =>
                                setLiveCraft((prev) => ({
                                  ...prev,
                                  theme: event.target.value,
                                }))
                              }
                            >
                              <option value="">Any theme</option>
                              {(liveCraftOptions?.filter_options?.themes || []).map((row) => (
                                <option key={row.value} value={row.value}>
                                  {row.label}
                                  {row.count ? ` (${row.count})` : ""}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label>
                            Rating
                            <select
                              data-testid="live-channels-craft-rating"
                              value={liveCraft.content_rating || ""}
                              onChange={(event) =>
                                setLiveCraft((prev) => ({
                                  ...prev,
                                  content_rating: event.target.value,
                                }))
                              }
                            >
                              <option value="">Any rating</option>
                              {(liveCraftOptions?.filter_options?.content_ratings || []).map(
                                (row) => (
                                  <option key={row.value} value={row.value}>
                                    {row.label}
                                    {row.count ? ` (${row.count})` : ""}
                                  </option>
                                ),
                              )}
                            </select>
                          </label>
                          <div className="wizard-actions">
                            <button
                              type="button"
                              className="ghost"
                              data-testid="live-channels-craft-preview"
                              disabled={liveCraftPreviewBusy}
                              onClick={async () => {
                                setLiveCraftPreviewBusy(true);
                                try {
                                  const result = await previewLiveChannelsCraft({
                                    media_scope: liveCraft.media_scope || "both",
                                    collection_id:
                                      liveCraft.source === "collection"
                                        ? liveCraft.collection_id
                                        : "",
                                    craft_filters: buildCraftFiltersPayload(liveCraft),
                                  });
                                  setLiveCraftPreview(result);
                                } catch (error) {
                                  setLiveCraftPreview({
                                    matched: 0,
                                    note: error.message || "Preview failed.",
                                  });
                                } finally {
                                  setLiveCraftPreviewBusy(false);
                                }
                              }}
                            >
                              {liveCraftPreviewBusy ? "Counting…" : "Preview match count"}
                            </button>
                            {liveCraftPreview ? (
                              <p
                                className="wizard-note"
                                data-testid="live-channels-craft-preview-result"
                              >
                                {liveCraftPreview.note ||
                                  `Matched ${liveCraftPreview.matched ?? 0}` +
                                    (liveCraftPreview.match_total
                                      ? ` / ${liveCraftPreview.match_total}`
                                      : "")}
                              </p>
                            ) : null}
                          </div>
                        </div>
                      </div>
                      <div className="wizard-actions">
                        <button
                          type="button"
                          className="primary"
                          data-testid="live-channels-craft-publish"
                          disabled={liveBusy === "craft"}
                          onClick={async () => {
                            if (
                              !window.confirm(
                                "Publish this station to Tunarr? New channel numbers are remapped into Plex Live TV after publish.",
                              )
                            ) {
                              return;
                            }
                            const number = Number(liveCraft.number);
                            const craftFilters = buildCraftFiltersPayload(liveCraft);
                            await runPublishJob(
                              () =>
                                publishLiveChannelsChannel({
                                  name: liveCraft.name,
                                  number: Number.isFinite(number) ? number : 0,
                                  source: liveCraft.source,
                                  programming_mode: liveCraft.programming_mode,
                                  media_scope: liveCraft.media_scope || "both",
                                  motif: liveCraft.motif,
                                  cluster_tag: liveCraft.cluster_tag,
                                  collection_id: liveCraft.collection_id,
                                  collection_title: liveCraft.collection_title,
                                  youth_safe:
                                    liveCraft.youth_safe || liveCraft.source === "youth",
                                  craft_filters: craftFilters,
                                  fill_programming: true,
                                }),
                              {
                                busyKey: "craft",
                                block: "craft",
                                successFallback: "Station published.",
                              },
                            );
                            try {
                              const opts = await getLiveChannelsCraftOptions();
                              setLiveCraftOptions(opts);
                              setLiveCraft((prev) => ({
                                ...prev,
                                name: "",
                                number: String(opts.next_channel_number || 100),
                              }));
                            } catch {
                              /* ignore */
                            }
                          }}
                        >
                          {liveBusy === "craft" ? "Publishing…" : "Publish station"}
                        </button>
                      </div>
                      {renderPublishProgress("craft")}
                      {renderLiveBlockAlert("craft")}
                    </div>

                    <div
                      className="live-channels-craft-block"
                      data-testid="live-channels-from-collection"
                    >
                      <h4>From a collection</h4>
                      <p className="wizard-note">
                        One-tap station from a Plex collection or published Projectionist
                        list. Sequential keeps collection order; Shuffle randomizes that
                        pool; Chaos draws wider from your TV/Movies libraries.
                      </p>
                      {liveCraftOptions?.collections_error ? (
                        <p
                          className="wizard-note"
                          data-testid="live-channels-collections-error"
                        >
                          {liveCraftOptions.collections_error}
                        </p>
                      ) : null}
                      {!(liveCraftOptions?.collections || []).length ? (
                        <p
                          className="wizard-note"
                          data-testid="live-channels-collections-empty"
                        >
                          {liveCraftOptions?.collections_empty_hint ||
                            "No collections available yet. Create one in Plex, or publish a list under Collections."}
                        </p>
                      ) : null}
                      <label className="field">
                        <span>Programming</span>
                        <select
                          data-testid="live-channels-collection-mode"
                          value={liveCraft.programming_mode || "sequential"}
                          onChange={(event) =>
                            setLiveCraft((prev) => ({
                              ...prev,
                              programming_mode: event.target.value,
                            }))
                          }
                        >
                          <option value="sequential">Sequential — collection order</option>
                          <option value="shuffle">Shuffle — randomize this collection</option>
                          <option value="chaos">Chaos — wider random in TV/Movies</option>
                        </select>
                      </label>
                      <div className="wizard-actions">
                        <button
                          type="button"
                          className="ghost"
                          data-testid="live-channels-publish-collection"
                          disabled={
                            liveBusy === "collection" ||
                            !(liveCraftOptions?.collections || []).length
                          }
                          onClick={async () => {
                            const first = (liveCraftOptions?.collections || [])[0];
                            if (!first) return;
                            const picked =
                              (liveCraft.collection_id &&
                                (liveCraftOptions?.collections || []).find(
                                  (row) => row.id === liveCraft.collection_id,
                                )) ||
                              first;
                            const mode = liveCraft.programming_mode || "sequential";
                            const modeLabel =
                              mode === "shuffle"
                                ? "Shuffle"
                                : mode === "chaos"
                                  ? "Chaos"
                                  : "Sequential";
                            if (
                              !window.confirm(
                                `Publish “${picked.title}” as a ${modeLabel} Live Channel station?`,
                              )
                            ) {
                              return;
                            }
                            await runPublishJob(
                              () =>
                                publishLiveChannelsFromCollection({
                                  collection_id: picked.id,
                                  collection_title: picked.title,
                                  name: picked.title,
                                  programming_mode: mode,
                                  media_scope: liveCraft.media_scope || "both",
                                  craft_filters: buildCraftFiltersPayload(liveCraft),
                                }),
                              {
                                busyKey: "collection",
                                block: "collection",
                                successFallback: `Published “${picked.title}”.`,
                              },
                            );
                          }}
                        >
                          {liveBusy === "collection"
                            ? "Publishing…"
                            : (liveCraftOptions?.collections || []).length
                              ? `Publish “${
                                  (
                                    (liveCraft.collection_id &&
                                      (liveCraftOptions?.collections || []).find(
                                        (row) => row.id === liveCraft.collection_id,
                                      )) ||
                                    liveCraftOptions.collections[0]
                                  )?.title
                                }”`
                              : "No collections available"}
                        </button>
                      </div>
                      {renderPublishProgress("collection")}
                      {renderLiveBlockAlert("collection")}
                    </div>

                    <div className="live-channels-craft-block">
                      <h4>Starter pack</h4>
                      <p className="wizard-note">
                        Propose 2–4 library-aware stations (taste, motifs, collections, Chaos /
                        youth-safe), then publish the ones you want. Re-running is additive —
                        existing channel numbers keep their stations; only missing numbers are created.
                      </p>
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
                                  "Create / publish the selected starter stations? Existing channel numbers keep their stations; empty lineups are filled from your Plex library.",
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
                                const result = await publishLiveChannelsStarters({
                                  recipes,
                                  fill_programming: true,
                                });
                                const feedback = formatPublishFeedback(result);
                                setActionFeedback("live-channels",
                                  feedback.type,
                                  feedback.summary, { block: "publish",  details: feedback.details },
                                );
                                const status = await getLiveChannelsStatus();
                                setLiveChannelsStatus(status);
                              } catch (error) {
                                setActionFeedback("live-channels", "error", error.message, { block: "publish" });
                              } finally {
                                setLiveBusy(null);
                              }
                            }}
                          >
                            {liveBusy === "publish" ? "Publishing…" : "Publish selected starters"}
                          </button>
                        </div>
                        {renderLiveBlockAlert("publish")}
                      </>
                    ) : (
                      <p className="wizard-note">
                        Click Propose starters above for 2–4 stations from your library signals.
                      </p>
                    )}
                    </div>
                  </div>

                  <div className="service-card" data-testid="live-channels-manage">
                    <div className="service-card-header">
                      <div className="service-card-title">
                        <h3>Your stations</h3>
                      </div>
                      <div className="service-card-actions">
                        <button
                          type="button"
                          className="ghost"
                          data-testid="live-channels-repair-continuity"
                          disabled={liveBusy === "continuity-repair"}
                          onClick={async () => {
                            if (
                              !window.confirm(
                                "Repair continuity on all stations? This remounts filler paths if needed, attaches the shared filler list, pads commercial-cut gaps (up to 15 minutes), and warms streams. Active Live TV sessions may briefly drop while Tunarr restarts.",
                              )
                            ) {
                              return;
                            }
                            try {
                              await runContinuityJob(
                                {
                                  rescan: true,
                                  repair: true,
                                  refill_lineups: true,
                                },
                                { successFallback: "Continuity repair finished.", block: "stations" },
                              );
                            } catch {
                              /* feedback already set */
                            }
                          }}
                        >
                          {liveBusy === "continuity-repair"
                            ? "Repairing…"
                            : "Repair continuity"}
                        </button>
                        <button
                          type="button"
                          className="ghost"
                          data-testid="live-channels-refresh-manage"
                          disabled={liveBusy === "manage-refresh"}
                          onClick={async () => {
                            setLiveBusy("manage-refresh");
                            try {
                              setLiveChannelsStatus(await getLiveChannelsStatus());
                            } catch (error) {
                              setActionFeedback("live-channels", "error", error.message, { block: "stations" });
                            } finally {
                              setLiveBusy(null);
                            }
                          }}
                        >
                          Refresh
                        </button>
                      </div>
                    </div>
                    <p className="wizard-note">
                      Lineup depth, media scope, and continuity show here. Refill re-pulls titles;
                      Settings sets TV / Movies / Both; Repair continuity fixes jump-start stations
                      in place.
                    </p>
                    {liveLaunched && effectiveLiveTab === "stations"
                      ? renderContinuityProgress()
                      : null}
                    {renderLiveBlockAlert("stations")}
                    {(liveChannelsStatus?.continuity?.checks || []).length ? (
                      <ul
                        className="live-channels-check-list"
                        data-testid="live-channels-continuity-checks-stations"
                      >
                        {liveChannelsStatus.continuity.checks.map((check) => (
                          <LiveStatusCheck
                            key={check.id}
                            ok={check.ok}
                            soft={check.soft}
                            testId={`live-channels-continuity-${check.id}`}
                          >
                            {check.label}: {check.message}
                          </LiveStatusCheck>
                        ))}
                      </ul>
                    ) : null}
                    {(liveChannelsStatus?.guide_index?.lineup?.channels ||
                      liveChannelsStatus?.channels ||
                      []).length ? (
                      <ul className="wizard-note live-channels-manage-list" data-testid="live-channels-manage-list">
                        {(
                          liveChannelsStatus?.guide_index?.lineup?.channels ||
                          liveChannelsStatus?.channels ||
                          []
                        ).map((ch) => {
                          const id = ch.id || ch.channel_id;
                          const programs =
                            ch.total_programs != null ? Number(ch.total_programs) : null;
                          const statusRow = (liveChannelsStatus?.channels || []).find(
                            (row) => (row.id || row.channel_id) === id,
                          );
                          const mediaScope =
                            statusRow?.media_scope || ch.media_scope || "both";
                          const hasContinuity = Boolean(
                            statusRow?.has_continuity ?? ch.has_continuity,
                          );
                          return (
                            <li key={id || `${ch.number}:${ch.name}`}>
                              <div className="live-channels-manage-row">
                                <span>
                                  {ch.number != null ? `${ch.number} · ` : ""}
                                  {ch.name || "Station"}
                                  {programs != null
                                    ? programs > 0
                                      ? ` — ${programs} titles in lineup`
                                      : " — empty lineup (refill after scan)"
                                    : ""}
                                  {` · ${mediaScope === "tv" ? "TV" : mediaScope === "movies" ? "Movies" : "Both"}`}
                                  {hasContinuity ? " · continuity ✓" : " · continuity needed"}
                                </span>
                                <span className="live-channels-manage-actions">
                                  <button
                                    type="button"
                                    className="ghost"
                                    data-testid={`live-channels-settings-${id}`}
                                    disabled={!id}
                                    onClick={() =>
                                      setStationSettingsOpen(
                                        stationSettingsOpen === id ? null : id,
                                      )
                                    }
                                  >
                                    Settings
                                  </button>
                                  <button
                                    type="button"
                                    className="ghost"
                                    data-testid={`live-channels-refill-${id}`}
                                    disabled={!id || liveBusy === `refill-${id}`}
                                    onClick={async () => {
                                      if (!id) return;
                                      if (!window.confirm(`Refill lineup for ${ch.name}?`)) return;
                                      setLiveBusy(`refill-${id}`);
                                      try {
                                        const result = await refillLiveChannelsChannel(id, {
                                          recipe: { media_scope: mediaScope },
                                        });
                                        setActionFeedback("live-channels",
                                          result.ok ? "success" : "error",
                                          result.note || "Refill finished.",
                                          { block: "stations" },
                                        );
                                        setLiveChannelsStatus(await getLiveChannelsStatus());
                                      } catch (error) {
                                        setActionFeedback("live-channels", "error", error.message, { block: "stations" });
                                      } finally {
                                        setLiveBusy(null);
                                      }
                                    }}
                                  >
                                    {liveBusy === `refill-${id}` ? "Refilling…" : "Refill"}
                                  </button>
                                  <button
                                    type="button"
                                    className="ghost"
                                    data-testid={`live-channels-delete-${id}`}
                                    disabled={!id || liveBusy === `delete-${id}`}
                                    onClick={async () => {
                                      if (!id) return;
                                      if (
                                        !window.confirm(
                                          `Delete station ${ch.number != null ? ch.number + " · " : ""}${ch.name}? This cannot be undone.`,
                                        )
                                      ) {
                                        return;
                                      }
                                      setLiveBusy(`delete-${id}`);
                                      try {
                                        await deleteLiveChannelsChannel(id);
                                        setActionFeedback("live-channels",
                                          "success",
                                          `Deleted ${ch.name}.`,
                                          { block: "stations" },
                                        );
                                        setLiveChannelsStatus(await getLiveChannelsStatus());
                                        setLiveCraftOptions(await getLiveChannelsCraftOptions());
                                      } catch (error) {
                                        setActionFeedback("live-channels", "error", error.message, { block: "stations" });
                                      } finally {
                                        setLiveBusy(null);
                                      }
                                    }}
                                  >
                                    {liveBusy === `delete-${id}` ? "Deleting…" : "Delete"}
                                  </button>
                                </span>
                              </div>
                              {stationSettingsOpen === id ? (
                                <div
                                  className="live-channels-station-settings"
                                  data-testid={`live-channels-station-settings-${id}`}
                                >
                                  <label>
                                    Media scope
                                    <select
                                      data-testid={`live-channels-station-scope-${id}`}
                                      defaultValue={mediaScope}
                                      onChange={async (event) => {
                                        const next = event.target.value;
                                        setLiveBusy(`settings-${id}`);
                                        try {
                                          const result = await patchLiveChannelsStationSettings(
                                            id,
                                            { media_scope: next },
                                          );
                                          setActionFeedback("live-channels",
                                            "success",
                                            result.message || "Station settings saved.",
                                            { block: "stations" },
                                        );
                                          setLiveChannelsStatus(await getLiveChannelsStatus());
                                        } catch (error) {
                                          setActionFeedback("live-channels",
                                            "error",
                                            error.message,
                                            { block: "stations" },
                                        );
                                        } finally {
                                          setLiveBusy(null);
                                        }
                                      }}
                                    >
                                      <option value="tv">TV</option>
                                      <option value="movies">Movies</option>
                                      <option value="both">Both</option>
                                    </select>
                                  </label>
                                  <p className="wizard-note">
                                    Refill after changing scope so the lineup only uses matching
                                    libraries. Continuity fillers stay shared across stations.
                                  </p>
                                </div>
                              ) : null}
                            </li>
                          );
                        })}
                      </ul>
                    ) : (
                      <p className="wizard-note" data-testid="live-channels-manage-empty">
                        No stations on Tunarr yet — craft one above or publish a starter pack.
                      </p>
                    )}
                  </div>

                  </>
                  ) : null}

                  {!liveLaunched || effectiveLiveTab === "setup" ? (
                  <>
                  <div
                    className={`service-card${
                      liveAttach?.discovery?.ok ||
                      liveChannelsStatus?.guide_index?.last_attach?.ok
                        ? " service-ok"
                        : ""
                    }`}
                    data-testid="live-channels-plex-attach"
                  >
                    <div className="service-card-header">
                      <div className="service-card-title">
                        {!liveLaunched ? (
                          <p className="live-channels-step-label">
                            Step {settings?.tunarr?.docker_orchestration ? "5" : "4"}
                          </p>
                        ) : null}
                        <h3>Add Tunarr beside your tuners in Plex</h3>
                        <LiveReadyBadge
                          ready={Boolean(
                            liveAttach?.discovery?.ok ||
                              liveChannelsStatus?.guide_index?.last_attach?.ok,
                          )}
                          label="Attached"
                          testId="live-channels-attach-ready"
                        />
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
                              setActionFeedback("live-channels", "error", error.message, { block: "connection" });
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
                            liveBusy === "plex-repair" ||
                            Boolean(liveAttach?.needs_lan_url)
                          }
                          onClick={async () => {
                            setLiveBusy("attach-guide");
                            try {
                              if (!liveAttach) {
                                setLiveAttach(await getLiveChannelsPlexAttach());
                              }
                              const result = await postLiveChannelsPlexAttachGuide();
                              const mappedNote =
                                result.expected != null
                                  ? ` Mapped ${result.mapped ?? 0}/${result.expected}.`
                                  : "";
                              setActionFeedback(
                                "live-channels",
                                "success",
                                `${result.message || "Tunarr XMLTV guide attached in Plex (OTA left alone)."}${mappedNote}`,
                                { block: "attach" },
                              );
                              try {
                                setLiveChannelsStatus(await getLiveChannelsStatus());
                              } catch {
                                /* status refresh best-effort */
                              }
                            } catch (error) {
                              setActionFeedback("live-channels", "error", error.message, { block: "attach" });
                            } finally {
                              setLiveBusy(null);
                            }
                          }}
                        >
                          {liveBusy === "attach-guide"
                            ? "Attaching guide…"
                            : "Attach Tunarr guide in Plex"}
                        </button>
                        <button
                          type="button"
                          className="ghost"
                          data-testid="live-channels-plex-repair"
                          disabled={
                            liveBusy === "attach" ||
                            liveBusy === "attach-guide" ||
                            liveBusy === "plex-repair" ||
                            Boolean(liveAttach?.needs_lan_url)
                          }
                          onClick={async () => {
                            if (
                              !window.confirm(
                                "Repair Plex tuner/guide? This recreates the Tunarr device and XMLTV DVR in Plex (OTA stays), rescans all channels, and remaps the guide. Active Live TV sessions on Tunarr channels may drop briefly.",
                              )
                            ) {
                              return;
                            }
                            setLiveBusy("plex-repair");
                            try {
                              const result = await postLiveChannelsPlexRepair();
                              const mappedNote =
                                result.expected != null
                                  ? ` Mapped ${result.mapped ?? 0}/${result.expected}.`
                                  : "";
                              setActionFeedback(
                                "live-channels",
                                "success",
                                `${result.message || "Plex Tunarr tuner/guide repaired."}${mappedNote}`,
                                { block: "attach" },
                              );
                              try {
                                setLiveChannelsStatus(await getLiveChannelsStatus());
                              } catch {
                                /* status refresh best-effort */
                              }
                            } catch (error) {
                              setActionFeedback("live-channels", "error", error.message, { block: "attach" });
                            } finally {
                              setLiveBusy(null);
                            }
                          }}
                        >
                          {liveBusy === "plex-repair" ? "Repairing…" : "Repair Plex tuner/guide"}
                        </button>
                      </div>
                    </div>
                    {renderLiveBlockAlert("attach")}
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
                        <ul className="live-channels-check-list">
                          <LiveStatusCheck ok={Boolean(liveAttach.discovery?.ok)} soft={!liveAttach.discovery?.ok}>
                            {liveAttach.discovery?.message || "Discovery not checked."}
                          </LiveStatusCheck>
                          {liveChannelsStatus?.guide_index?.last_attach?.ok ? (
                            <LiveStatusCheck ok>
                              Guide attached
                              {liveChannelsStatus.guide_index.last_attach.dvr_key
                                ? ` · DVR ${liveChannelsStatus.guide_index.last_attach.dvr_key}`
                                : ""}
                            </LiveStatusCheck>
                          ) : null}
                        </ul>
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
                  </>
                  ) : null}
                </div>
              </>
            )}

            {/* Live Channels feedback is inline per card via liveBlockFeedback. */}
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

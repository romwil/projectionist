/**
 * SPA payload types for JSON the UI actually reads.
 * Wire JSON is `unknown` at `api()`; wrappers and callers narrow to these.
 * Intersect with JsonObject so extra fields the UI already reads stay accessible.
 */

export type JsonObject = {
  // Converted JS reads heterogeneous JSON; indexed fields must stay open.
  [key: string]: any;
};

/** Converted JS helper arg: wire JSON is untyped; callee narrows. */
export type JsParam = any;

export type MediaType = "movie" | "show" | "episode" | "collection" | "tv" | string;

/** Named-bridge poster why-line (XC-01). Pipeline labels are not this. */
export type RecommendationExplanation = JsonObject & {
  kind?: string;
  sentence?: string;
};

export type RecommendationWhy = JsonObject & {
  explanation?: RecommendationExplanation;
  sentence?: string;
};

/** Poster/card `reason` may be a sentence string or a why object. */
export type RecommendationReason = string | RecommendationWhy | RecommendationExplanation | null | undefined;

export type LibraryItem = JsonObject & {
  id?: string | number;
  rating_key?: string;
  play_rating_key?: string;
  plex_rating_key?: string;
  tmdb_id?: number | string | null;
  tvdb_id?: number | string | null;
  title?: string;
  year?: number | string | null;
  media_type?: MediaType;
  poster_url?: string;
  in_library?: boolean;
  in_radarr?: boolean;
  in_sonarr?: boolean;
  already_queued?: boolean;
  watch_state?: string;
  view_count?: number | null;
  view_offset_ms?: number | null;
  duration_ms?: number | null;
  last_viewed_at?: string | null;
  total_episode_count?: number | null;
  unwatched_episode_count?: number | null;
  resume_label?: string;
  explanation?: RecommendationExplanation;
  why?: RecommendationWhy;
  card_kind?: string;
  continue_season?: number | null;
  continue_episode?: number | null;
  continue_episode_title?: string;
  season?: number | null;
  episode?: number | null;
};

export type ChatBlock = JsonObject & {
  type?: string;
  content?: string;
  items?: LibraryItem[];
};

export type ChatMessage = JsonObject & {
  id?: string;
  role?: string;
  content?: string;
  blocks?: ChatBlock[];
  session_id?: string;
};

export type ChatThread = JsonObject & {
  id?: string;
  title?: string;
  updated_at?: string | number;
};

export type AuthUser = JsonObject & {
  id?: string;
  username?: string;
  role?: string;
  is_youth?: boolean;
  disabled?: boolean;
};

export type FeatureFlags = JsonObject & {
  multi_user_enabled?: boolean;
  seerr_enabled?: boolean;
  plex_collections_enabled?: boolean;
  live_channels_enabled?: boolean;
  live_channels_ready?: boolean;
  access_requests_enabled?: boolean;
  agent_may_mutate_personal_data?: boolean;
  invite_only?: boolean;
  open_auto_provision?: boolean;
  ephemeral_collection_gc_enabled?: boolean;
  ephemeral_collection_gc_dry_run?: boolean;
};

export type Features = JsonObject & {
  features?: FeatureFlags;
  request_path?: string;
  setup_state?: string;
  auth_methods?: string[] | Record<string, unknown>;
  oidc_provider_name?: string;
  household_domain?: string;
  user?: AuthUser | null;
  arr?: Record<string, boolean | undefined>;
  notifications?: JsonObject & {
    channels?: unknown;
    mail_configured?: boolean;
  };
  auth?: JsonObject & { oidc_provider_name?: string };
};

export type JobProgress = JsonObject & {
  percent?: number;
  phase?: string;
  message?: string;
  label?: string;
  current?: number;
  total?: number;
};

export type Job = JsonObject & {
  id?: string;
  status?: string;
  job_type?: string;
  type?: string;
  error?: string;
  progress?: JobProgress;
};

export type HubRail = JsonObject & {
  feed?: string;
  items?: LibraryItem[];
  total?: number;
  note?: string | null;
  pending?: boolean;
};

/** Explore (and similar) hub payloads: `warming` must stay a server flag. */
export type HubWarming = JsonObject & {
  warming?: boolean;
};

export type ExploreHubPayload = HubWarming & {
  rails?: Record<string, HubRail | undefined>;
};

export type AuthMe = JsonObject & {
  authenticated?: boolean;
  user?: AuthUser | null;
};

export type QueryParams = Record<string, string | number | boolean | null | undefined>;

export type ApiError = Error & {
  status?: number;
  code?: string;
  conflict?: unknown;
};

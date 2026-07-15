"""Pydantic schemas for API and agent payloads."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from curatorx.connectors.plex import normalize_stars


MediaType = Literal["movie", "show"]


class TitleCard(BaseModel):
    media_type: MediaType
    title: str
    year: Optional[int] = None
    tmdb_id: Optional[int] = None
    tvdb_id: Optional[int] = None
    rating_key: Optional[str] = None
    poster_url: str = ""
    backdrop_url: str = ""
    overview: str = ""
    rating: Optional[float] = None
    genres: List[str] = Field(default_factory=list)
    in_library: bool = False
    in_radarr: bool = False
    in_sonarr: bool = False
    recommendation_reason: str = ""
    facet_matches: List[str] = Field(default_factory=list)
    runtime_minutes: Optional[int] = None
    user_stars: Optional[int] = None
    total_episode_count: Optional[int] = None
    unwatched_episode_count: Optional[int] = None
    card_kind: Optional[str] = None


class TitleDetail(TitleCard):
    cast: List[str] = Field(default_factory=list)
    directors: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    file_size_bytes: int = 0
    view_count: int = 0
    last_viewed_at: Optional[int] = None
    arr_id: Optional[int] = None
    purge_score: Optional[float] = None
    purge_reason: str = ""


class ChatMessageBlock(BaseModel):
    type: Literal["text", "title_cards", "action_prompt"]
    content: str = ""
    items: List[TitleCard] = Field(default_factory=list)
    action: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    id: str
    role: Literal["user", "assistant", "system"]
    blocks: List[ChatMessageBlock] = Field(default_factory=list)
    created_at: float = 0
    lens_id: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    lens_id: Optional[str] = None
    persona_id: Optional[str] = None


class ActionConfirmRequest(BaseModel):
    token: str
    confirmed: bool = True


class PreferenceSignal(BaseModel):
    signal_type: Literal["explicit", "positive", "negative", "add", "dismiss"]
    text: str = ""
    tmdb_id: Optional[int] = None
    tvdb_id: Optional[int] = None
    media_type: Optional[MediaType] = None
    lens_id: Optional[str] = None
    cluster_tag: Optional[str] = None
    weight: Optional[float] = None
    explicit_lock: Optional[bool] = None


class ViewportPayload(BaseModel):
    title: str = ""
    items: List[TitleCard] = Field(default_factory=list)


class Lens(BaseModel):
    lens_id: str
    lens_name: str
    description: str = ""
    created_at: Optional[str] = None


class LensCreate(BaseModel):
    lens_id: str = Field(..., min_length=1)
    lens_name: str = Field(..., min_length=1)
    description: str = ""


class LensUpdate(BaseModel):
    lens_name: Optional[str] = None
    description: Optional[str] = None


class ActiveLensPayload(BaseModel):
    lens_id: str


class PersonaPresetSummary(BaseModel):
    id: str
    name: str
    description: str
    tagline: str = ""
    val_bro_prof: float
    val_dipl_snark: float
    val_pass_auto: float
    identity_blurb: str = ""
    behavioral_anchor: str = ""
    typing_phrases: List[str] = Field(default_factory=list)
    composer_placeholders: List[str] = Field(default_factory=list)
    welcome_greeting: str = ""
    welcome_starters: List[str] = Field(default_factory=list)
    review_prompt_templates: Dict[str, str] = Field(default_factory=dict)
    accent_hue: str = ""


class PersonaUiCopy(BaseModel):
    typing_phrases: List[str] = Field(default_factory=list)
    composer_placeholders: List[str] = Field(default_factory=list)
    welcome_greeting: str = ""
    welcome_starters: List[str] = Field(default_factory=list)
    review_prompt_templates: Dict[str, str] = Field(default_factory=dict)
    accent_hue: str = ""
    job_status_phrases: List[str] = Field(default_factory=list)
    preset_tagline: str = ""
    preset_name: str = ""


class PersonaMetrics(BaseModel):
    metric_id: str = "current_profile"
    curator_name: str = "Curator"
    persona_identity: str = ""
    val_bro_prof: float = Field(default=0.5, ge=0.0, le=1.0)
    val_dipl_snark: float = Field(default=0.5, ge=0.0, le=1.0)
    val_pass_auto: float = Field(default=0.5, ge=0.0, le=1.0)
    persona_preset_id: Optional[str] = None
    persona_prompt_override: Optional[str] = None
    persona_mode: str = "sliders"
    behavioral_prompt: str = ""
    assembled_prompt: str = ""
    persona_ui: Optional["PersonaUiCopy"] = None
    last_modified: Optional[str] = None


class PersonaMetricsUpdate(BaseModel):
    curator_name: Optional[str] = None
    persona_identity: Optional[str] = None
    val_bro_prof: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    val_dipl_snark: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    val_pass_auto: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    persona_preset_id: Optional[str] = None
    persona_prompt_override: Optional[str] = None
    clear_persona_override: bool = False
    apply_preset: Optional[str] = None


class PersonaPreviewResponse(BaseModel):
    persona_mode: str
    behavioral_prompt: str
    assembled_prompt: str


class SystemConfigEntry(BaseModel):
    config_key: str
    config_value: str


class SystemConfigUpdate(BaseModel):
    values: Dict[str, str] = Field(default_factory=dict)


class MessageFeedbackRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    feedback: Optional[Literal["helpful", "not_helpful"]] = None


class LensTasteEntry(BaseModel):
    lens_id: str
    cluster_tag: str
    weight: float = 1.0
    explicit_lock: bool = False
    last_updated: Optional[str] = None


class UserReviewCreate(BaseModel):
    rating_key: Optional[str] = None
    tmdb_id: Optional[int] = None
    tvdb_id: Optional[int] = None
    media_type: MediaType
    title: str = Field(..., min_length=1)
    stars: float = Field(..., ge=0.5, le=5)
    review_text: str = ""
    review_tags: List[str] = Field(default_factory=list)
    prompted_by: str = "user"
    session_id: Optional[str] = None
    lens_id: Optional[str] = None
    prompt_id: Optional[str] = None
    replace_plex_rating: bool = False

    @field_validator("stars")
    @classmethod
    def _normalize_half_stars(cls, value: float) -> float:
        return normalize_stars(value)


class UserReview(BaseModel):
    id: str
    rating_key: Optional[str] = None
    tmdb_id: Optional[int] = None
    tvdb_id: Optional[int] = None
    media_type: MediaType
    title: str
    stars: float
    review_text: str = ""
    review_tags: List[str] = Field(default_factory=list)
    prompted_by: str = "user"
    session_id: Optional[str] = None
    lens_id: Optional[str] = None
    plex_rating_synced: bool = False
    plex_synced_at: Optional[float] = None
    created_at: float
    updated_at: float

    @field_validator("stars")
    @classmethod
    def _normalize_half_stars(cls, value: float) -> float:
        return normalize_stars(value)


class RatingPrompt(BaseModel):
    id: str
    rating_key: str
    media_type: MediaType
    title: str
    completion_pct: float
    detected_at: float
    prompted_at: Optional[float] = None
    dismissed_at: Optional[float] = None
    review_id: Optional[str] = None


class WatchlistPin(BaseModel):
    id: str
    user_id: Optional[str] = None
    tmdb_id: Optional[int] = None
    tvdb_id: Optional[int] = None
    media_type: MediaType
    title: str
    created_at: float
    plex_rating_key: Optional[str] = None


class WatchlistCreate(BaseModel):
    tmdb_id: Optional[int] = None
    tvdb_id: Optional[int] = None
    media_type: MediaType
    title: str = Field(..., min_length=1)


class WatchlistListResponse(BaseModel):
    items: List[WatchlistPin] = Field(default_factory=list)
    count: int = 0


class WatchlistSyncSettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    pull_on_login: Optional[bool] = None
    push_on_pin: Optional[bool] = None


class WatchlistSyncRequest(BaseModel):
    direction: str = "both"


class CuratedListItem(BaseModel):
    id: str
    list_id: str
    tmdb_id: Optional[int] = None
    tvdb_id: Optional[int] = None
    media_type: MediaType
    title: str
    library_item_id: Optional[int] = None
    position: int = 0
    created_at: float


class CuratedList(BaseModel):
    id: str
    user_id: Optional[str] = None
    name: str
    description: str = ""
    created_at: float
    updated_at: float
    item_count: int = 0
    items: Optional[List[CuratedListItem]] = None


class CuratedListCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""


class CuratedListUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = None


class CuratedListItemCreate(BaseModel):
    tmdb_id: Optional[int] = None
    tvdb_id: Optional[int] = None
    media_type: MediaType
    title: str = Field(..., min_length=1)
    library_item_id: Optional[int] = None


class CuratedListCollectionResponse(BaseModel):
    items: List[CuratedList] = Field(default_factory=list)
    count: int = 0


class EngagementStreakResponse(BaseModel):
    session_count_30d: int = 0
    streak_visible: bool = False


# --- Persona Templates (per-conversation persona selection) ---


class PersonaTemplate(BaseModel):
    """A reusable persona configuration with 7 behavioral sliders.

    Personas come in three visibility tiers:
    - ``builtin``: shipped with CuratorX, immutable (Classic Curator, etc.)
    - ``shared``: created by the server owner, visible to all users
    - ``private``: created by an individual user, visible only to them
    """

    id: str
    name: str
    visibility: str
    owner_user_id: Optional[str] = None
    val_bro_prof: float = Field(default=0.5, ge=0.0, le=1.0)
    val_dipl_snark: float = Field(default=0.5, ge=0.0, le=1.0)
    val_pass_auto: float = Field(default=0.5, ge=0.0, le=1.0)
    val_depth: float = Field(default=0.5, ge=0.0, le=1.0)
    val_obscurity: float = Field(default=0.5, ge=0.0, le=1.0)
    val_verbosity: float = Field(default=0.5, ge=0.0, le=1.0)
    val_formality: float = Field(default=0.5, ge=0.0, le=1.0)
    system_prompt_override: Optional[str] = None
    accent_color: Optional[str] = None
    is_default: bool = False
    created_at: Optional[str] = None


class PersonaTemplateCreate(BaseModel):
    """Payload for creating a new persona template (all 7 sliders validated)."""

    name: str = Field(..., min_length=1, max_length=100)
    val_bro_prof: float = Field(default=0.5, ge=0.0, le=1.0)
    val_dipl_snark: float = Field(default=0.5, ge=0.0, le=1.0)
    val_pass_auto: float = Field(default=0.5, ge=0.0, le=1.0)
    val_depth: float = Field(default=0.5, ge=0.0, le=1.0)
    val_obscurity: float = Field(default=0.5, ge=0.0, le=1.0)
    val_verbosity: float = Field(default=0.5, ge=0.0, le=1.0)
    val_formality: float = Field(default=0.5, ge=0.0, le=1.0)
    system_prompt_override: Optional[str] = None
    accent_color: Optional[str] = None


class PersonaTemplateUpdate(BaseModel):
    """Payload for updating a persona template (all fields optional)."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    val_bro_prof: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    val_dipl_snark: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    val_pass_auto: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    val_depth: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    val_obscurity: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    val_verbosity: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    val_formality: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    system_prompt_override: Optional[str] = None
    accent_color: Optional[str] = None

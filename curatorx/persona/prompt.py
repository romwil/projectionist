"""Assemble persona prompts for the Curator agent."""

from __future__ import annotations

from typing import Any, Literal, Mapping, Optional

from curatorx.persona.presets import get_preset

CURATOR_NAME_PLACEHOLDER = "{curator_name}"

SliderBand = Literal["low", "mid", "high"]

VOCABULARY_GUIDANCE: dict[SliderBand, str] = {
    "low": (
        "Voice: casual film-fan — contractions, couch-talk, and shorthand (\"that third-act turn\"). "
        "Assume shared literacy; don't lecture on film history unless asked. "
        "Name-check directors when it matters; quote dialogue over formal scene breakdowns."
    ),
    "mid": (
        "Voice: balanced film-literate — accessible by default, precise when it earns its place. "
        "Explain craft or context only when it clarifies why a pick fits. "
        "Match the user's energy: breezy for comfort nights, sharper for deep cuts."
    ),
    "high": (
        "Voice: professorial cineaste — precise vocabulary (mise-en-scène, diegetic sound, neo-noir, New Hollywood). "
        "Anchor picks in movements, influences, and auteur context. "
        "Substantive like seminar notes; never pedantic for its own sake."
    ),
}

DIRECTNESS_GUIDANCE: dict[SliderBand, str] = {
    "low": (
        "Tone: diplomatic — build context before recommendations; soften critiques with alternatives. "
        "Frame weak fits as \"might not land for your taste\" rather than blunt rejection. "
        "Highlight what works even when steering away from a title."
    ),
    "mid": (
        "Tone: even-handed — honest assessments with clear rationale; no unnecessary padding. "
        "Call out mismatch plainly but offer a constructive pivot. "
        "Balance praise and critique proportionally to fit."
    ),
    "high": (
        "Tone: direct and snark-capable — lead with conclusions (\"skip this\", \"queue tonight\") before the why. "
        "Call out weak picks, overhyped titles, and dead-end series without sugarcoating. "
        "Dry wit and pointed comparisons are fine; affectionate roasts, not cruelty."
    ),
}

INITIATIVE_GUIDANCE: dict[SliderBand, str] = {
    "low": (
        "Initiative: passive — suggest options; never assume the user wants a title queued. "
        "Present two or three choices and let them steer. "
        "Wait for explicit approval before proposing Radarr/Sonarr adds."
    ),
    "mid": (
        "Initiative: collaborative — propose a shortlist with a recommended first pick. "
        "Offer next steps (\"want me to queue the top one?\") but don't act unilaterally. "
        "Structure binge plans and gap lists when asked, with checkpoints."
    ),
    "high": (
        "Initiative: autonomous — propose concrete next steps: queue order, purge priority, tonight's stack. "
        "When confidence is high, lead with a single best pick and the action to take. "
        "Surface patterns proactively (\"your sci-fi cluster hasn't moved in months\")."
    ),
}

LIBRARY_CURATION_BLOCK = (
    "Library curation: ground every pick in their Plex collection via tools — owned titles, gaps, and watch patterns. "
    "Title cards must carry a specific recommendation_reason tied to their taste, not generic praise or pipeline labels "
    "(never 'TMDB title match'). Pass reason on search_tmdb or call set_recommendation_reasons after attaching cards. "
    "Respect confirmation tokens for fleet changes; never add or remove without explicit approval. "
    "Never re-offer titles already confirmed/queued this session or marked in_radarr/in_sonarr/already_queued — "
    "those are done; pick different gaps instead."
)

REVIEW_ENGAGEMENT_BLOCK = (
    "Review memory: before recommending, call get_user_reviews when you need past ratings, notes, or star patterns — "
    "weigh high-star clusters and avoid re-pushing titles they scored low unless they ask for a second look. "
    "When the user asks to rate/review recently watched titles, call suggest_titles_to_rate — the UI shows rateable "
    "cards (half-stars allowed). Prefer that batch card path over grilling one title at a time in chat. "
    "Optional chat Q&A via start_review_dialogue is enrichment only, not the default for \"rate my last 10\". "
    "Accept fractional stars (e.g. 4.5) via save_user_review — never ask the user to round half-stars to integers. "
    "When the user mentions finishing, nearly finishing, or rewatching a single title, a quick review prompt is fine."
)

DISAGREEMENT_GUIDANCE: dict[SliderBand, dict[SliderBand, str]] = {
    "low": {
        "low": "When they disagree, explore what missed — mood, pacing, or era — and offer gentler alternatives.",
        "mid": "When they disagree, acknowledge quickly and pivot to two better-aligned options.",
        "high": "When they disagree, adjust the plan immediately with a revised shortlist and rationale.",
    },
    "mid": {
        "low": "When they disagree, ask one clarifying question, then re-rank without defensiveness.",
        "mid": "When they disagree, restate the mismatch and propose a clear alternative lane.",
        "high": "When they disagree, concede the miss plainly and lead with a stronger replacement pick.",
    },
    "high": {
        "low": "When they disagree, accept it — their taste wins; offer a softer backup without debate.",
        "mid": "When they disagree, say what you got wrong and name the taste signal you will weight next time.",
        "high": "When they disagree, own the miss in one line and immediately propose the better pick you should have led with.",
    },
}

PACING_GUIDANCE: dict[SliderBand, str] = {
    "low": "Pacing: unfold recommendations — context, comparison, then pick. Use short paragraphs.",
    "mid": "Pacing: lead with the pick, follow with two or three sentences of why. Expand only if asked.",
    "high": "Pacing: headline first — verdict, then bullets. No preamble unless the user asked for analysis.",
}


def persona_row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, Mapping):
        return dict(row)
    return dict(row) if hasattr(row, "keys") else {}


def derive_persona_mode(persona: Mapping[str, Any]) -> str:
    override = str(persona.get("persona_prompt_override") or "").strip()
    return "custom" if override else "sliders"


def substitute_curator_name(text: str, curator_name: Optional[str] = None) -> str:
    """Replace ``{curator_name}`` placeholders with the resolved display name."""
    name = str(curator_name or "Curator").strip() or "Curator"
    return text.replace(CURATOR_NAME_PLACEHOLDER, name)


def slider_band(value: float) -> SliderBand:
    """Map a 0–1 slider position to low, mid, or high behavioral band."""
    if value < 0.35:
        return "low"
    if value > 0.65:
        return "high"
    return "mid"


def _slider_label(value: float, low: str, mid: str, high: str) -> str:
    return {"low": low, "mid": mid, "high": high}[slider_band(value)]


def build_behavioral_prompt_from_sliders(persona: Mapping[str, Any]) -> str:
    """Slider-generated behavioral template; name is a ``{curator_name}`` placeholder."""
    bro = float(persona.get("val_bro_prof") or 0.5)
    snark = float(persona.get("val_dipl_snark") or 0.5)
    auto = float(persona.get("val_pass_auto") or 0.5)

    vocab_band = slider_band(bro)
    direct_band = slider_band(snark)
    init_band = slider_band(auto)

    preset_id = persona.get("persona_preset_id")
    preset = get_preset(str(preset_id) if preset_id else None)

    sections: list[str] = [
        f"Display name: {CURATOR_NAME_PLACEHOLDER}.",
    ]

    if preset:
        sections.append(
            f"Archetype anchor: {preset.name} — {preset.tagline}. "
            f"Sliders fine-tune this base; preserve its core voice."
        )
        if preset.behavioral_anchor:
            sections.append(preset.behavioral_anchor)

    sections.extend(
        [
            (
                f"Vocabulary ({_slider_label(bro, 'bro', 'balanced', 'professorial')}, {bro:.2f}): "
                f"{VOCABULARY_GUIDANCE[vocab_band]}"
            ),
            (
                f"Directness ({_slider_label(snark, 'diplomatic', 'even-tempered', 'snarky')}, {snark:.2f}): "
                f"{DIRECTNESS_GUIDANCE[direct_band]}"
            ),
            (
                f"Initiative ({_slider_label(auto, 'passive', 'collaborative', 'autonomous')}, {auto:.2f}): "
                f"{INITIATIVE_GUIDANCE[init_band]}"
            ),
            f"Recommendation pacing: {PACING_GUIDANCE[direct_band]}",
            f"When the user disagrees: {DISAGREEMENT_GUIDANCE[direct_band][init_band]}",
            LIBRARY_CURATION_BLOCK,
            "Apply these behavioral dimensions consistently in every reply.",
        ]
    )

    return "\n\n".join(sections)


def build_rendered_behavioral_prompt(persona: Mapping[str, Any]) -> str:
    """Behavioral prompt with curator name substituted for display and agent injection."""
    override = str(persona.get("persona_prompt_override") or "").strip()
    template = override if override else build_behavioral_prompt_from_sliders(persona)
    return substitute_curator_name(template, persona.get("curator_name"))


def build_persona_prompt(persona: Mapping[str, Any]) -> str:
    """Behavioral + identity block injected into the system prompt."""
    parts: list[str] = []
    identity = str(persona.get("persona_identity") or "").strip()
    if identity:
        parts.append(substitute_curator_name(identity, persona.get("curator_name")))

    parts.append(build_rendered_behavioral_prompt(persona))
    parts.append(REVIEW_ENGAGEMENT_BLOCK)

    if not parts:
        return ""
    return "\n\n".join(parts) + "\n"


def build_assembled_persona_prompt(persona: Mapping[str, Any]) -> str:
    """Full persona section as shown in the config preview (same as agent injection)."""
    return build_persona_prompt(persona).strip()

"""Persona presets and prompt assembly."""

from projectionist.persona.presets import (
    PERSONA_PRESETS,
    accent_hue_for,
    composer_placeholders_for,
    format_review_prompt,
    get_preset,
    list_presets,
    persona_ui_for,
    review_prompt_template_for,
    typing_phrases_for,
    welcome_greeting_for,
    welcome_starters_for,
)
from projectionist.persona.prompt import (
    CURATOR_NAME_PLACEHOLDER,
    build_assembled_persona_prompt,
    build_behavioral_prompt_from_sliders,
    build_persona_prompt,
    build_rendered_behavioral_prompt,
    derive_persona_mode,
    persona_row_to_dict,
    slider_band,
    substitute_curator_name,
)

__all__ = [
    "PERSONA_PRESETS",
    "CURATOR_NAME_PLACEHOLDER",
    "accent_hue_for",
    "build_assembled_persona_prompt",
    "build_behavioral_prompt_from_sliders",
    "build_persona_prompt",
    "build_rendered_behavioral_prompt",
    "composer_placeholders_for",
    "derive_persona_mode",
    "format_review_prompt",
    "get_preset",
    "list_presets",
    "persona_row_to_dict",
    "persona_ui_for",
    "review_prompt_template_for",
    "slider_band",
    "substitute_curator_name",
    "typing_phrases_for",
    "welcome_greeting_for",
    "welcome_starters_for",
]

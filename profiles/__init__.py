from profiles.catalog import (
    EditRules,
    PROFILE_DEFINITIONS,
    STYLE_PRESETS,
    ProfileDefinition,
    StylePreset,
    get_edit_rules,
    get_profile_definition,
    get_style_preset,
    profile_names,
    styles_for_profile,
)


# Compatibilidade com a primeira versão do perfil YouTube.
YouTubeEditRules = EditRules


def get_youtube_rules(style):
    return get_edit_rules("YouTube", style)


__all__ = [
    "EditRules",
    "PROFILE_DEFINITIONS",
    "STYLE_PRESETS",
    "ProfileDefinition",
    "StylePreset",
    "YouTubeEditRules",
    "get_edit_rules",
    "get_profile_definition",
    "get_style_preset",
    "get_youtube_rules",
    "profile_names",
    "styles_for_profile",
]

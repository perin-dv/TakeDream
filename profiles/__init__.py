from profiles.catalog import (
    EditRules,
    PROFILE_DEFINITIONS,
    ProfileDefinition,
    get_edit_rules,
    get_profile_definition,
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
    "ProfileDefinition",
    "YouTubeEditRules",
    "get_edit_rules",
    "get_profile_definition",
    "get_youtube_rules",
    "profile_names",
    "styles_for_profile",
]

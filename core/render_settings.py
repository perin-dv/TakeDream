from copy import deepcopy

from renderer.captions import CAPTION_STYLES
from renderer.formats import (
    get_aspect_ratio,
)


DEFAULT_CAPTION_STYLE = "Dinâmica"


def default_render_settings(project):
    aspect_ratio = (
        project.get("aspect_ratio")
        or "16:9"
    )

    try:
        get_aspect_ratio(aspect_ratio)
    except ValueError:
        aspect_ratio = "16:9"

    return {
        "aspect_ratio": aspect_ratio,
        "captions_enabled": False,
        "caption_style": (
            DEFAULT_CAPTION_STYLE
        ),
        "auto_zoom": False,
    }


def normalize_render_settings(
    settings,
    project,
):
    result = default_render_settings(
        project
    )

    if isinstance(settings, dict):
        result.update(
            {
                key: deepcopy(value)
                for key, value in settings.items()
                if key in result
            }
        )

    aspect = get_aspect_ratio(
        result["aspect_ratio"]
    )
    result["aspect_ratio"] = aspect.key

    result["captions_enabled"] = bool(
        result["captions_enabled"]
    )
    result["auto_zoom"] = bool(
        result["auto_zoom"]
    )

    if (
        result["caption_style"]
        not in CAPTION_STYLES
    ):
        result["caption_style"] = (
            DEFAULT_CAPTION_STYLE
        )

    return result

from copy import deepcopy

from profiles import get_style_preset
from renderer.audio import (
    DEFAULT_AUDIO_SETTINGS,
    normalize_audio_settings,
)
from renderer.captions import CAPTION_STYLES
from renderer.formats import (
    get_aspect_ratio,
)
from renderer.reframe import (
    normalize_focus_region,
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

    captions_enabled = False
    caption_style = DEFAULT_CAPTION_STYLE
    auto_zoom = False

    try:
        preset = get_style_preset(
            project.get("style", "Clean")
        )
    except ValueError:
        preset = None

    if preset is not None:
        captions_enabled = (
            preset.captions_enabled
        )
        caption_style = (
            preset.caption_style
        )
        auto_zoom = preset.auto_zoom

    focus = normalize_focus_region(
        project.get("focus_region")
    )

    return {
        "aspect_ratio": aspect_ratio,
        "captions_enabled": captions_enabled,
        "caption_style": caption_style,
        "auto_zoom": auto_zoom,
        "smart_reframe": True,
        "focus_region": focus.to_dict(),
        "audio_enhance": True,
        "audio_settings": dict(
            DEFAULT_AUDIO_SETTINGS
        ),
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
    result["smart_reframe"] = bool(
        result["smart_reframe"]
    )
    result["audio_enhance"] = bool(
        result["audio_enhance"]
    )

    if (
        result["caption_style"]
        not in CAPTION_STYLES
    ):
        result["caption_style"] = (
            DEFAULT_CAPTION_STYLE
        )

    result["focus_region"] = (
        normalize_focus_region(
            result.get("focus_region")
        ).to_dict()
    )

    audio_settings = normalize_audio_settings(
        result.get("audio_settings")
    )
    audio_settings["enabled"] = (
        result["audio_enhance"]
        and audio_settings["enabled"]
    )
    result["audio_settings"] = (
        audio_settings
    )

    return result

from pathlib import Path

from core.content_pipeline import load_content_analysis
from core.processing import ProcessingError
from core.project_manager import ProjectManager
from core.results import validate_transcript
from core.storage import read_json
from profiles import get_style_preset
from renderer.captions import write_ass_captions
from renderer.formats import target_dimensions


CAPTION_PATH = "decisions/captions.ass"
TRANSCRIPT_PATH = "transcription/transcript.json"


def prepare_caption_file(
    root,
    project,
    edit_plan,
    settings,
    tools,
    source,
):
    if not settings["captions_enabled"]:
        return None

    transcript_path = root / TRANSCRIPT_PATH
    if not transcript_path.exists():
        raise ProcessingError("A transcrição é necessária para gerar legendas.")

    try:
        transcript = validate_transcript(read_json(transcript_path))
    except ValueError as error:
        raise ProcessingError(
            f"Transcrição inválida para legendas: {error}"
        ) from error

    metadata = ProjectManager().load_media_metadata(root) or tools.probe(source)
    width = metadata.get("video", {}).get("width")
    height = metadata.get("video", {}).get("height")

    if type(width) is not int or type(height) is not int:
        raise ProcessingError("Não foi possível determinar a resolução para as legendas.")

    play_res_x, play_res_y = target_dimensions(
        width,
        height,
        settings["aspect_ratio"],
        short_side=None,
    )

    caption_file = root / CAPTION_PATH
    write_ass_captions(
        transcript,
        edit_plan,
        caption_file,
        style=settings["caption_style"],
        play_res_x=play_res_x,
        play_res_y=play_res_y,
    )
    return caption_file


def _fallback_zoom_events(root):
    """Create safe punch-zoom events when the user explicitly enables zoom.

    Wedding presets intentionally default to no automatic zoom. The UI toggle,
    however, is an explicit user override and must not silently result in zero
    effects merely because the preset's semantic analyzer disabled suggestions.
    """
    try:
        manager = ProjectManager()
        _, project = manager.load_project(root)
    except ValueError:
        return []

    duration_ms = project.get("wedding_assembly_duration_ms")
    if type(duration_ms) is not int or duration_ms <= 0:
        duration_ms = project.get("edited_duration_ms")
    if type(duration_ms) is not int or duration_ms <= 0:
        metadata = manager.load_media_metadata(root) or {}
        seconds = metadata.get("container", {}).get("duration_seconds")
        if isinstance(seconds, (int, float)) and seconds > 0:
            duration_ms = int(round(seconds * 1000))

    if type(duration_ms) is not int or duration_ms <= 0:
        return []

    try:
        preset = get_style_preset(project.get("style", "Clean"))
        gap_ms = max(7000, min(int(preset.zoom_gap_ms), 18000))
        scale = max(1.03, float(preset.zoom_scale))
    except ValueError:
        gap_ms = 12000
        scale = 1.04

    events = []
    cursor = min(2500, max(0, duration_ms // 8))
    while cursor < duration_ms:
        end = min(duration_ms, cursor + 2400)
        if end - cursor >= 500:
            events.append(
                {
                    "start_ms": cursor,
                    "end_ms": end,
                    "scale": min(scale, 1.10),
                    "reason": "user_enabled_auto_zoom",
                }
            )
        cursor += gap_ms
    return events


def zoom_events_for_settings(root, settings):
    if not settings["auto_zoom"]:
        return []

    analysis = load_content_analysis(root)
    if analysis:
        events = analysis.get("zoom_events", [])
        if isinstance(events, list) and events:
            return events

    # Manual toggle wins over a conservative style preset. This also gives
    # wedding/montage projects real zoom events even when semantic suggestions
    # are intentionally disabled by the preset.
    return _fallback_zoom_events(root)

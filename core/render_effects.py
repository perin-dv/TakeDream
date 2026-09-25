from pathlib import Path

from core.content_pipeline import (
    load_content_analysis,
)
from core.processing import (
    ProcessingError,
)
from core.project_manager import ProjectManager
from core.results import validate_transcript
from core.storage import read_json
from renderer.captions import (
    write_ass_captions,
)
from renderer.formats import (
    target_dimensions,
)


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
        raise ProcessingError(
            "A transcrição é necessária para gerar legendas."
        )

    try:
        transcript = validate_transcript(
            read_json(transcript_path)
        )
    except ValueError as error:
        raise ProcessingError(
            f"Transcrição inválida para legendas: {error}"
        ) from error

    metadata = (
        ProjectManager().load_media_metadata(
            root
        )
        or tools.probe(source)
    )

    width = metadata.get(
        "video",
        {},
    ).get("width")
    height = metadata.get(
        "video",
        {},
    ).get("height")

    if (
        type(width) is not int
        or type(height) is not int
    ):
        raise ProcessingError(
            "Não foi possível determinar a resolução para as legendas."
        )

    play_res_x, play_res_y = (
        target_dimensions(
            width,
            height,
            settings["aspect_ratio"],
            short_side=None,
        )
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


def zoom_events_for_settings(
    root,
    settings,
):
    if not settings["auto_zoom"]:
        return []

    analysis = load_content_analysis(
        root
    )
    if not analysis:
        return []

    events = analysis.get(
        "zoom_events",
        [],
    )
    return (
        events
        if isinstance(events, list)
        else []
    )

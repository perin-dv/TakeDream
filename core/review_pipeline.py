from pathlib import Path

from core.content_pipeline import (
    load_content_analysis,
)
from core.processing import (
    ProcessingError,
    check_cancelled,
)
from core.project_manager import ProjectManager
from core.render_settings import (
    normalize_render_settings,
)
from core.results import validate_transcript
from core.storage import (
    read_json,
    write_json,
)
from editor.edit_plan import validate_edit_plan
from media.ffmpeg_tools import FFmpegTools
from renderer.captions import (
    write_ass_captions,
)
from renderer.ffmpeg_renderer import (
    FFmpegRenderer,
)
from renderer.formats import (
    get_aspect_ratio,
    target_dimensions,
)


EDIT_PLAN_PATH = "decisions/edit_plan.json"
CAPTION_PATH = "decisions/captions.ass"
TRANSCRIPT_PATH = "transcription/transcript.json"


def _resolve_source(root, project):
    source = Path(
        project["source"]["original_path"]
    )
    if not source.is_absolute():
        source = root / source
    return source


def _next_preview_path(root):
    output_dir = Path(root) / "output"
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    candidate = (
        output_dir
        / "video_editado-review.mp4"
    )
    if not candidate.exists():
        return candidate

    counter = 2
    while True:
        candidate = (
            output_dir
            / f"video_editado-review-{counter}.mp4"
        )
        if not candidate.exists():
            return candidate
        counter += 1


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


class ReviewRenderPipeline:
    def __init__(
        self,
        manager=None,
        tools=None,
        renderer=None,
    ):
        self.manager = (
            manager
            or ProjectManager()
        )
        self.tools = (
            tools
            or FFmpegTools()
        )
        self.renderer = (
            renderer
            or FFmpegRenderer(self.tools)
        )

    def run(
        self,
        project_dir,
        edit_plan,
        *,
        render_settings=None,
        cancel=None,
        stage=lambda text: None,
        progress=lambda value: None,
    ):
        root, project = (
            self.manager.load_project(
                project_dir
            )
        )
        validate_edit_plan(edit_plan)
        check_cancelled(cancel)

        settings = normalize_render_settings(
            render_settings,
            project,
        )

        source = _resolve_source(
            root,
            project,
        )
        if not source.exists():
            raise ProcessingError(
                "O vídeo original não foi encontrado para gerar a nova prévia."
            )

        stage(
            "Preparando formato, legendas e efeitos..."
        )
        progress(5)

        caption_file = prepare_caption_file(
            root,
            project,
            edit_plan,
            settings,
            self.tools,
            source,
        )
        zoom_events = zoom_events_for_settings(
            root,
            settings,
        )

        destination = _next_preview_path(
            root
        )

        stage("Renderizando nova prévia...")
        progress(8)

        rendered = self.renderer.render(
            source,
            destination,
            edit_plan,
            cancel=cancel,
            target_aspect_ratio=(
                settings["aspect_ratio"]
            ),
            caption_file=caption_file,
            zoom_events=zoom_events,
            progress=progress,
            stage=stage,
        )

        check_cancelled(cancel)

        stage(
            "Salvando ajustes da timeline..."
        )
        write_json(
            root / EDIT_PLAN_PATH,
            edit_plan,
        )

        relative_output = str(
            rendered.relative_to(root)
        ).replace("\\", "/")

        aspect = get_aspect_ratio(
            settings["aspect_ratio"]
        )

        output_size = getattr(
            self.renderer,
            "last_output_size",
            None,
        )

        self.manager.update_processing(
            root,
            "review_rendered",
            edit_plan_path=EDIT_PLAN_PATH,
            output_path=relative_output,
            edit_cuts=edit_plan[
                "stats"
            ]["cuts"],
            original_duration_ms=edit_plan[
                "source_duration_ms"
            ],
            edited_duration_ms=edit_plan[
                "stats"
            ][
                "estimated_duration_ms"
            ],
            render_encoder=getattr(
                getattr(
                    self.renderer,
                    "last_encoder",
                    None,
                ),
                "label",
                "Desconhecido",
            ),
            review_settings=settings,
            aspect_ratio=aspect.key,
            orientation=aspect.orientation,
            preview_width=(
                output_size[0]
                if output_size
                else None
            ),
            preview_height=(
                output_size[1]
                if output_size
                else None
            ),
        )

        progress(100)
        stage("Nova prévia pronta.")

        return {
            "edit_plan": edit_plan,
            "output_path": relative_output,
            "review_settings": settings,
            "render_encoder": getattr(
                getattr(
                    self.renderer,
                    "last_encoder",
                    None,
                ),
                "label",
                "Desconhecido",
            ),
        }

from pathlib import Path

from core.processing import ProcessingError, check_cancelled
from core.project_manager import ProjectManager
from core.storage import write_json
from editor.edit_plan import validate_edit_plan
from media.ffmpeg_tools import FFmpegTools
from renderer.ffmpeg_renderer import FFmpegRenderer


EDIT_PLAN_PATH = "decisions/edit_plan.json"


def _resolve_source(root, project):
    source = Path(project["source"]["original_path"])
    if not source.is_absolute():
        source = root / source
    return source


def _next_preview_path(root):
    output_dir = Path(root) / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    candidate = output_dir / "video_editado-review.mp4"
    if not candidate.exists():
        return candidate

    counter = 2
    while True:
        candidate = output_dir / f"video_editado-review-{counter}.mp4"
        if not candidate.exists():
            return candidate
        counter += 1


class ReviewRenderPipeline:
    def __init__(self, manager=None, tools=None, renderer=None):
        self.manager = manager or ProjectManager()
        self.tools = tools or FFmpegTools()
        self.renderer = renderer or FFmpegRenderer(self.tools)

    def run(
        self,
        project_dir,
        edit_plan,
        *,
        cancel=None,
        stage=lambda text: None,
        progress=lambda value: None,
    ):
        root, project = self.manager.load_project(project_dir)
        validate_edit_plan(edit_plan)
        check_cancelled(cancel)

        source = _resolve_source(root, project)
        if not source.exists():
            raise ProcessingError(
                "O vídeo original não foi encontrado para gerar a nova prévia."
            )

        destination = _next_preview_path(root)

        stage("Renderizando nova prévia...")
        progress(-1)
        rendered = self.renderer.render(
            source,
            destination,
            edit_plan,
            cancel=cancel,
        )

        check_cancelled(cancel)

        stage("Salvando ajustes da linha do tempo...")
        write_json(root / EDIT_PLAN_PATH, edit_plan)

        relative_output = str(rendered.relative_to(root)).replace("\\", "/")
        self.manager.update_processing(
            root,
            "review_rendered",
            edit_plan_path=EDIT_PLAN_PATH,
            output_path=relative_output,
            edit_cuts=edit_plan["stats"]["cuts"],
            original_duration_ms=edit_plan["source_duration_ms"],
            edited_duration_ms=edit_plan["stats"]["estimated_duration_ms"],
        )

        progress(100)
        stage("Nova prévia pronta.")

        return {
            "edit_plan": edit_plan,
            "output_path": relative_output,
        }

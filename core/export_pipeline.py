from pathlib import Path

from core.edit_pipeline import load_edit_state
from core.processing import ProcessingError, check_cancelled
from core.project_manager import ProjectManager
from media.ffmpeg_tools import FFmpegTools
from renderer.export_profiles import get_export_profile
from renderer.ffmpeg_renderer import FFmpegRenderer


def _resolve_source(root, project):
    source = Path(project["source"]["original_path"])
    if not source.is_absolute():
        source = root / source
    return source


def _next_export_path(root, profile_key):
    export_dir = Path(root) / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)

    candidate = export_dir / f"video_final_{profile_key}.mp4"
    if not candidate.exists():
        return candidate

    counter = 2
    while True:
        candidate = export_dir / f"video_final_{profile_key}-{counter}.mp4"
        if not candidate.exists():
            return candidate
        counter += 1


class ExportPipeline:
    def __init__(self, manager=None, tools=None, renderer=None):
        self.manager = manager or ProjectManager()
        self.tools = tools or FFmpegTools()
        self.renderer = renderer or FFmpegRenderer(self.tools)

    def run(
        self,
        project_dir,
        profile_key,
        *,
        cancel=None,
        stage=lambda text: None,
        progress=lambda value: None,
    ):
        root, project = self.manager.load_project(project_dir)
        state = load_edit_state(root)

        if state["edit_errors"]:
            raise ProcessingError("\n".join(state["edit_errors"]))

        edit_plan = state["edit_plan"]
        if edit_plan is None:
            raise ProcessingError(
                "Nenhum plano de edição válido foi encontrado para exportar."
            )

        profile = get_export_profile(profile_key)
        source = _resolve_source(root, project)

        if not source.exists():
            raise ProcessingError(
                "O vídeo original não foi encontrado para exportação."
            )

        check_cancelled(cancel)

        destination = _next_export_path(root, profile.key)

        stage(f"Exportando vídeo em {profile.label}...")
        progress(-1)

        rendered = self.renderer.render(
            source,
            destination,
            edit_plan,
            cancel=cancel,
            output_height=profile.height,
            crf=profile.crf,
            audio_bitrate=profile.audio_bitrate,
            preset=profile.preset,
        )

        check_cancelled(cancel)

        relative_output = str(rendered.relative_to(root)).replace("\\", "/")
        self.manager.update_processing(
            root,
            "exported",
            last_export_path=relative_output,
            last_export_profile=profile.key,
        )

        progress(100)
        stage("Exportação concluída.")

        return {
            "export_path": relative_output,
            "export_profile": profile.key,
            "export_label": profile.label,
        }

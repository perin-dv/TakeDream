import os
import shutil
import tempfile
from pathlib import Path

from core.edit_pipeline import load_edit_state
from core.processing import (
    ProcessingError,
    check_cancelled,
)
from core.project_manager import ProjectManager
from core.render_effects import (
    prepare_caption_file,
    zoom_events_for_settings,
)
from core.render_settings import (
    normalize_render_settings,
)
from media.ffmpeg_tools import FFmpegTools
from renderer.export_profiles import (
    get_export_profile,
)
from renderer.ffmpeg_renderer import (
    FFmpegRenderer,
)
from renderer.formats import (
    target_dimensions,
)


def _resolve_source(root, project):
    source = Path(
        project["source"]["original_path"]
    )
    if not source.is_absolute():
        source = root / source
    return source


def _next_export_path(
    root,
    profile_key,
    aspect_ratio,
):
    export_dir = Path(root) / "exports"
    export_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    aspect_key = str(
        aspect_ratio
    ).replace(":", "x")

    candidate = (
        export_dir
        / (
            f"video_final_{profile_key}_"
            f"{aspect_key}.mp4"
        )
    )
    if not candidate.exists():
        return candidate

    counter = 2
    while True:
        candidate = (
            export_dir
            / (
                f"video_final_{profile_key}_"
                f"{aspect_key}-{counter}.mp4"
            )
        )
        if not candidate.exists():
            return candidate
        counter += 1


def _copy_preview(
    preview,
    destination,
    cancel=None,
):
    check_cancelled(cancel)

    fd, temporary = tempfile.mkstemp(
        suffix=".mp4",
        prefix=".export-",
        dir=destination.parent,
    )
    os.close(fd)
    Path(temporary).unlink(
        missing_ok=True
    )

    try:
        shutil.copy2(
            preview,
            temporary,
        )
        check_cancelled(cancel)
        os.replace(
            temporary,
            destination,
        )
    finally:
        Path(temporary).unlink(
            missing_ok=True
        )

    return destination


class ExportPipeline:
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
        profile_key,
        *,
        cancel=None,
        stage=lambda text: None,
        progress=lambda value: None,
    ):
        root, project = (
            self.manager.load_project(
                project_dir
            )
        )
        state = load_edit_state(root)

        if state["edit_errors"]:
            raise ProcessingError(
                "\n".join(
                    state["edit_errors"]
                )
            )

        edit_plan = state["edit_plan"]
        if edit_plan is None:
            raise ProcessingError(
                "Nenhum plano de edição válido foi encontrado para exportar."
            )

        settings = normalize_render_settings(
            project.get(
                "review_settings"
            ),
            project,
        )

        profile = get_export_profile(
            profile_key
        )
        source = _resolve_source(
            root,
            project,
        )

        if not source.exists():
            raise ProcessingError(
                "O vídeo original não foi encontrado para exportação."
            )

        check_cancelled(cancel)

        destination = _next_export_path(
            root,
            profile.key,
            settings["aspect_ratio"],
        )

        preview_path = None
        preview_metadata = None

        if state.get("output_path"):
            candidate = (
                root / state["output_path"]
            ).resolve()

            if (
                candidate.exists()
                and candidate.is_file()
            ):
                preview_path = candidate

        can_reuse_preview = False

        if (
            preview_path is not None
            and profile.height is None
        ):
            can_reuse_preview = True

        elif (
            preview_path is not None
            and profile.height is not None
        ):
            try:
                preview_metadata = (
                    self.tools.probe(
                        preview_path,
                        cancel=cancel,
                    )
                )
                source_metadata = (
                    self.tools.probe(
                        source,
                        cancel=cancel,
                    )
                )

                source_width = (
                    source_metadata.get(
                        "video",
                        {},
                    ).get("width")
                )
                source_height = (
                    source_metadata.get(
                        "video",
                        {},
                    ).get("height")
                )
                preview_width = (
                    preview_metadata.get(
                        "video",
                        {},
                    ).get("width")
                )
                preview_height = (
                    preview_metadata.get(
                        "video",
                        {},
                    ).get("height")
                )

                if all(
                    type(value) is int
                    for value in (
                        source_width,
                        source_height,
                        preview_width,
                        preview_height,
                    )
                ):
                    expected = (
                        target_dimensions(
                            source_width,
                            source_height,
                            settings[
                                "aspect_ratio"
                            ],
                            short_side=(
                                profile.height
                            ),
                        )
                    )
                    can_reuse_preview = (
                        (
                            preview_width,
                            preview_height,
                        )
                        == expected
                    )

            except Exception:
                can_reuse_preview = False

        if can_reuse_preview:
            stage(
                f"Finalizando exportação "
                f"{profile.label} sem recomprimir..."
            )
            progress(30)

            rendered = _copy_preview(
                preview_path,
                destination,
                cancel=cancel,
            )
            export_mode = "smart_copy"

        else:
            stage(
                f"Preparando exportação "
                f"{profile.label}..."
            )
            progress(3)

            caption_file = (
                prepare_caption_file(
                    root,
                    project,
                    edit_plan,
                    settings,
                    self.tools,
                    source,
                )
            )
            zoom_events = (
                zoom_events_for_settings(
                    root,
                    settings,
                )
            )

            rendered = self.renderer.render(
                source,
                destination,
                edit_plan,
                cancel=cancel,
                output_height=profile.height,
                target_aspect_ratio=(
                    settings["aspect_ratio"]
                ),
                caption_file=caption_file,
                zoom_events=zoom_events,
                smart_reframe=(
                    settings["smart_reframe"]
                ),
                focus_region=(
                    settings["focus_region"]
                ),
                audio_settings=(
                    settings["audio_settings"]
                ),
                crf=profile.crf,
                audio_bitrate=(
                    profile.audio_bitrate
                ),
                preset=profile.preset,
                progress=progress,
                stage=stage,
            )
            export_mode = "render"

        check_cancelled(cancel)

        relative_output = str(
            rendered.relative_to(root)
        ).replace("\\", "/")

        encoder_label = (
            getattr(
                getattr(
                    self.renderer,
                    "last_encoder",
                    None,
                ),
                "label",
                "Desconhecido",
            )
            if export_mode == "render"
            else "Smart Copy"
        )

        self.manager.update_processing(
            root,
            "exported",
            last_export_path=(
                relative_output
            ),
            last_export_profile=(
                profile.key
            ),
            last_export_aspect_ratio=(
                settings["aspect_ratio"]
            ),
            last_export_mode=export_mode,
            last_export_encoder=(
                encoder_label
            ),
        )

        progress(100)
        stage("Exportação concluída.")

        return {
            "export_path": relative_output,
            "export_profile": profile.key,
            "export_label": profile.label,
            "export_aspect_ratio": (
                settings["aspect_ratio"]
            ),
            "export_mode": export_mode,
            "render_encoder": (
                encoder_label
            ),
        }

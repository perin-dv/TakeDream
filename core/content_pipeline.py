from pathlib import Path

from core.processing import ProcessingError, check_cancelled
from core.project_manager import ProjectManager
from core.storage import read_json, write_json
from editor.content_analysis import analyze_content
from media.ffmpeg_tools import FFmpegTools
from media.thumbnails import (
    generate_thumbnails,
    load_thumbnail_manifest,
)


CONTENT_ANALYSIS_PATH = "analysis/content_analysis.json"
SPEECH_SUGGESTIONS_PATH = "analysis/speech_suggestions.json"
BROLL_SUGGESTIONS_PATH = "analysis/broll_suggestions.json"
ZOOM_PLAN_PATH = "analysis/zoom_plan.json"
TRANSCRIPT_PATH = "transcription/transcript.json"


def load_content_analysis(project_dir):
    path = (
        Path(project_dir)
        / CONTENT_ANALYSIS_PATH
    )

    if not path.exists():
        return None

    try:
        data = read_json(path)
    except (OSError, ValueError):
        return None

    if (
        not isinstance(data, dict)
        or data.get("schema_version") != "0.1"
    ):
        return None

    return data


def _resolve_source(root, project):
    source = Path(
        project["source"]["original_path"]
    )

    if not source.is_absolute():
        source = root / source

    return source


class ContentPipeline:
    def __init__(self, manager=None, tools=None):
        self.manager = manager or ProjectManager()
        self.tools = tools or FFmpegTools()

    def run(
        self,
        project_dir,
        *,
        cancel=None,
        stage=lambda text: None,
        progress=lambda value: None,
    ):
        root, project = self.manager.load_project(
            project_dir
        )
        check_cancelled(cancel)

        transcript_path = root / TRANSCRIPT_PATH
        if not transcript_path.exists():
            raise ProcessingError(
                "Transcreva o projeto antes de analisar o conteúdo."
            )

        stage("Analisando fala e conteúdo...")
        progress(10)

        try:
            transcript = read_json(
                transcript_path
            )
        except (OSError, ValueError) as error:
            raise ProcessingError(
                f"Não foi possível ler a transcrição: {error}"
            ) from error

        analysis = analyze_content(
            transcript,
            profile=project.get(
                "profile",
                "YouTube",
            ),
            style=project.get(
                "style",
                "Dinâmico",
            ),
        )

        check_cancelled(cancel)
        write_json(
            root / CONTENT_ANALYSIS_PATH,
            analysis,
        )
        write_json(
            root / SPEECH_SUGGESTIONS_PATH,
            {
                "schema_version": "0.1",
                "items": analysis[
                    "speech_suggestions"
                ],
            },
        )
        write_json(
            root / BROLL_SUGGESTIONS_PATH,
            {
                "schema_version": "0.1",
                "items": analysis[
                    "broll_suggestions"
                ],
            },
        )
        write_json(
            root / ZOOM_PLAN_PATH,
            {
                "schema_version": "0.1",
                "items": analysis[
                    "zoom_events"
                ],
            },
        )

        progress(35)

        source = _resolve_source(
            root,
            project,
        )
        thumbnails = load_thumbnail_manifest(
            root
        )

        if (
            not thumbnails
            and source.exists()
            and self.tools.ffmpeg_path
        ):
            stage(
                "Gerando miniaturas da timeline..."
            )

            metadata = (
                self.manager.load_media_metadata(
                    root
                )
                or self.tools.probe(
                    source,
                    cancel=cancel,
                )
            )
            duration = (
                metadata.get(
                    "container",
                    {},
                ).get(
                    "duration_seconds"
                )
            )

            if isinstance(
                duration,
                (int, float),
            ) and duration > 0:
                thumbnails = generate_thumbnails(
                    project_dir=root,
                    source=source,
                    ffmpeg_path=self.tools.ffmpeg_path,
                    duration_seconds=float(
                        duration
                    ),
                    cancel=cancel,
                )

        check_cancelled(cancel)

        self.manager.update_processing(
            root,
            project.get(
                "status",
                "content_analyzed",
            ),
            content_analysis_path=(
                CONTENT_ANALYSIS_PATH
            ),
            content_analysis_engine=(
                analysis["engine"]
            ),
            speech_suggestions_path=(
                SPEECH_SUGGESTIONS_PATH
            ),
            broll_suggestions_path=(
                BROLL_SUGGESTIONS_PATH
            ),
            zoom_plan_path=ZOOM_PLAN_PATH,
        )

        progress(100)
        stage("Análise de conteúdo concluída.")

        return {
            "content_analysis": analysis,
            "thumbnail_paths": thumbnails,
        }

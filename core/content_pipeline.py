from pathlib import Path

from core.processing import ProcessingError, check_cancelled
from core.project_manager import ProjectManager
from core.storage import read_json, write_json
from core.wedding_story import STORY_LABELS
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
WEDDING_ASSEMBLY_PLAN_PATH = "decisions/wedding_assembly_plan.json"


def _load_wedding_story_overlay(project_dir):
    root = Path(project_dir)
    path = root / WEDDING_ASSEMBLY_PLAN_PATH
    if not path.exists():
        return None

    try:
        plan = read_json(path)
    except (OSError, ValueError):
        return None

    if not isinstance(plan, dict):
        return None
    clips = plan.get("clips")
    if not isinstance(clips, list) or not clips:
        return None

    blocks = []
    for clip in sorted(
        (item for item in clips if isinstance(item, dict)),
        key=lambda item: int(item.get("timeline_start_ms", 0) or 0),
    ):
        try:
            start_ms = int(clip.get("timeline_start_ms", 0) or 0)
            end_ms = int(clip.get("timeline_end_ms", start_ms) or start_ms)
        except (TypeError, ValueError):
            continue
        if end_ms <= start_ms:
            continue

        section = str(clip.get("story_section") or "nao_classificado")
        label = STORY_LABELS.get(section, section.replace("_", " ").title())
        confidence = float(clip.get("semantic_confidence", 0) or 0)

        if (
            blocks
            and blocks[-1]["section"] == section
            and start_ms <= blocks[-1]["end_ms"] + 5
        ):
            blocks[-1]["end_ms"] = end_ms
            blocks[-1]["clip_count"] += 1
            blocks[-1]["confidence_total"] += confidence
            blocks[-1]["confidence_samples"] += int(confidence > 0)
        else:
            blocks.append(
                {
                    "section": section,
                    "label": label,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "clip_count": 1,
                    "confidence_total": confidence,
                    "confidence_samples": int(confidence > 0),
                }
            )

    for block in blocks:
        samples = block.pop("confidence_samples", 0)
        total = block.pop("confidence_total", 0.0)
        block["semantic_confidence"] = (
            round(total / samples, 3)
            if samples
            else 0.0
        )
        block["duration_ms"] = block["end_ms"] - block["start_ms"]

    if not blocks:
        return None

    return {
        "schema_version": "0.1",
        "engine": "wedding-story-timeline-v2",
        "duration_ms": int(plan.get("estimated_duration_ms", blocks[-1]["end_ms"]) or 0),
        "clip_count": int(plan.get("clip_count", len(clips)) or len(clips)),
        "media_count": int(plan.get("media_count", 0) or 0),
        "story_builder": plan.get("story_builder"),
        "sections": plan.get("story_sections", []),
        "blocks": blocks,
    }


def load_content_analysis(project_dir):
    root = Path(project_dir)
    path = root / CONTENT_ANALYSIS_PATH
    data = None

    if path.exists():
        try:
            value = read_json(path)
        except (OSError, ValueError):
            value = None
        if (
            isinstance(value, dict)
            and value.get("schema_version") == "0.1"
        ):
            data = dict(value)

    wedding_story = _load_wedding_story_overlay(root)
    if data is None and wedding_story is None:
        return None

    if data is None:
        data = {
            "schema_version": "0.1",
            "engine": "timeline-v2-overlay",
            "summary": {
                "fillers": 0,
                "word_repetitions": 0,
                "possible_repetitions": 0,
                "broll_suggestions": 0,
                "zoom_events": 0,
            },
            "speech_suggestions": [],
            "broll_suggestions": [],
            "zoom_events": [],
        }

    if wedding_story is not None:
        data["wedding_story"] = wedding_story

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
            "content_analysis": load_content_analysis(root),
            "thumbnail_paths": thumbnails,
        }

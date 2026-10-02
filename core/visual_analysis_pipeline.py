from pathlib import Path

from core.processing import ProcessingError, check_cancelled
from core.project_manager import ProjectManager
from core.storage import write_json
from media.ffmpeg_tools import FFmpegTools
from media.visual_analyzer import VisualAnalyzer


VISUAL_ANALYSIS_PATH = "analysis/visual_analysis.json"
SCENE_ANALYSIS_PATH = "analysis/scene_analysis.json"
QUALITY_SCORES_PATH = "analysis/quality_scores.json"


def _resolve_source(root, project):
    source = Path(project["source"]["original_path"])
    if not source.is_absolute():
        source = root / source
    return source


class VisualAnalysisPipeline:
    def __init__(self, manager=None, tools=None, analyzer=None):
        self.manager = manager or ProjectManager()
        self.tools = tools or FFmpegTools()
        self.analyzer = analyzer

    def run(
        self,
        project_dir,
        *,
        metadata=None,
        cancel=None,
        stage=lambda text: None,
        progress=lambda value: None,
    ):
        root, project = self.manager.load_project(project_dir)
        source = _resolve_source(root, project)

        if not source.exists():
            raise ProcessingError("O vídeo original não foi encontrado para análise visual.")

        check_cancelled(cancel)

        if metadata is None:
            metadata = self.manager.load_media_metadata(root)
        if metadata is None:
            metadata = self.tools.probe(source, cancel=cancel)

        duration_seconds = metadata.get("container", {}).get("duration_seconds")
        if not isinstance(duration_seconds, (int, float)) or duration_seconds <= 0:
            raise ProcessingError("Não foi possível determinar a duração para análise visual.")

        duration_ms = int(round(duration_seconds * 1000))
        analyzer = self.analyzer or VisualAnalyzer(self.tools.ffmpeg_path)

        result = analyzer.analyze(
            source,
            duration_ms,
            cancel=cancel,
            stage=stage,
            progress=progress,
        )
        check_cancelled(cancel)

        write_json(root / VISUAL_ANALYSIS_PATH, result)
        write_json(
            root / SCENE_ANALYSIS_PATH,
            {
                "schema_version": result.get("schema_version", "0.1"),
                "scene_threshold": result.get("scene_threshold"),
                "scenes": [
                    {
                        key: value
                        for key, value in scene.items()
                        if key != "quality"
                    }
                    for scene in result.get("scenes", [])
                ],
            },
        )
        write_json(
            root / QUALITY_SCORES_PATH,
            {
                "schema_version": result.get("schema_version", "0.1"),
                "scores": [
                    {
                        "scene_id": scene["id"],
                        "start_ms": scene["start_ms"],
                        "end_ms": scene["end_ms"],
                        "sample_ms": scene.get("sample_ms"),
                        **scene["quality"],
                    }
                    for scene in result.get("scenes", [])
                    if isinstance(scene.get("quality"), dict)
                ],
            },
        )

        # Persist analysis paths without moving a project backwards in the pipeline.
        current_status = project.get("status", "media_analyzed")
        self.manager.update_processing(
            root,
            current_status,
            visual_analysis_path=VISUAL_ANALYSIS_PATH,
            scene_analysis_path=SCENE_ANALYSIS_PATH,
            quality_scores_path=QUALITY_SCORES_PATH,
            visual_scene_count=result.get("summary", {}).get("scene_count", 0),
            visual_quality_average=result.get("summary", {}).get("average_quality"),
        )

        return result

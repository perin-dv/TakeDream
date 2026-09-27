from datetime import datetime, timezone
from pathlib import Path

from core.media_library import (
    MEDIA_LIBRARY_PATH,
    load_media_library,
    save_media_library,
)
from core.processing import ProcessingError, check_cancelled
from core.project_manager import ProjectManager
from core.storage import write_json
from media.ffmpeg_tools import FFmpegTools
from media.visual_analyzer import VisualAnalyzer


BATCH_VISUAL_ANALYSIS_PATH = "analysis/batch_visual_analysis.json"
MEDIA_ASSET_ANALYSIS_DIR = "analysis/media_assets"


class BatchVisualAnalysisPipeline:
    def __init__(self, manager=None, tools=None, analyzer_factory=None):
        self.manager = manager or ProjectManager()
        self.tools = tools or FFmpegTools()
        self.analyzer_factory = analyzer_factory

    def _analyzer(self):
        if self.analyzer_factory is not None:
            return self.analyzer_factory()
        return VisualAnalyzer(self.tools.ffmpeg_path)

    def run(
        self,
        project_dir,
        *,
        cancel=None,
        stage=lambda text: None,
        progress=lambda value: None,
    ):
        root, project = self.manager.load_project(project_dir)
        library = load_media_library(root)
        if not library or not library.get("assets"):
            raise ProcessingError("O projeto não possui mídias na biblioteca.")

        assets = library["assets"]
        total = len(assets)
        all_candidates = []
        reused = 0
        analyzed = 0
        failed = 0

        for index, asset in enumerate(assets):
            check_cancelled(cancel)
            asset_path = Path(asset.get("path", ""))
            if not asset_path.exists():
                asset["analysis_status"] = "missing"
                asset["analysis_error"] = "Arquivo não encontrado."
                failed += 1
                continue

            visual_rel = asset.get("visual_analysis_path")
            visual_path = root / visual_rel if visual_rel else None
            if (
                asset.get("analysis_status") == "complete"
                and visual_path is not None
                and visual_path.exists()
            ):
                reused += 1
                cached = None
                try:
                    from core.storage import read_json
                    cached = read_json(visual_path)
                except (OSError, ValueError):
                    cached = None
                if isinstance(cached, dict):
                    self._collect_candidates(all_candidates, asset, cached)
                    progress(int(((index + 1) / total) * 100))
                    continue

            stage(
                f"Analisando mídia {index + 1}/{total}: {asset_path.name}"
            )

            try:
                metadata = self.tools.probe(asset_path, cancel=cancel)
                duration_seconds = metadata.get("container", {}).get("duration_seconds")
                if not isinstance(duration_seconds, (int, float)) or duration_seconds <= 0:
                    raise ProcessingError("Duração inválida para análise visual.")

                duration_ms = int(round(duration_seconds * 1000))
                analyzer = self._analyzer()
                base = int((index / total) * 100)
                span = max(1, int(100 / total))

                result = analyzer.analyze(
                    asset_path,
                    duration_ms,
                    cancel=cancel,
                    stage=lambda text, name=asset_path.name: stage(f"{name} • {text}"),
                    progress=lambda value, base=base, span=span: progress(
                        min(99, base + int((max(0, min(100, value)) / 100) * span))
                    ),
                )

                asset_dir = root / MEDIA_ASSET_ANALYSIS_DIR / asset["id"]
                asset_dir.mkdir(parents=True, exist_ok=True)
                metadata_path = asset_dir / "metadata.json"
                visual_path = asset_dir / "visual_analysis.json"
                write_json(metadata_path, metadata)
                write_json(visual_path, result)

                summary = result.get("summary", {})
                asset.update(
                    {
                        "analysis_status": "complete",
                        "analysis_error": None,
                        "analyzed_at": datetime.now(timezone.utc).isoformat(),
                        "metadata_path": str(metadata_path.relative_to(root)).replace("\\", "/"),
                        "visual_analysis_path": str(visual_path.relative_to(root)).replace("\\", "/"),
                        "duration_seconds": duration_seconds,
                        "resolution": metadata.get("video", {}).get("resolution"),
                        "fps": metadata.get("video", {}).get("fps"),
                        "scene_count": summary.get("scene_count", 0),
                        "quality_average": summary.get("average_quality"),
                    }
                )
                analyzed += 1
                self._collect_candidates(all_candidates, asset, result)
            except Exception as error:
                asset["analysis_status"] = "error"
                asset["analysis_error"] = str(error)
                failed += 1

            library["analyzed_count"] = sum(
                1 for item in assets if item.get("analysis_status") == "complete"
            )
            save_media_library(root, library)
            progress(int(((index + 1) / total) * 100))

        all_candidates.sort(key=lambda item: item.get("score", 0), reverse=True)
        summary = {
            "schema_version": "0.2",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "media_count": total,
            "analyzed_now": analyzed,
            "reused_from_cache": reused,
            "failed": failed,
            "total_scenes": sum(int(item.get("scene_count", 0) or 0) for item in assets),
            "best_take_candidates": all_candidates[:250],
        }
        write_json(root / BATCH_VISUAL_ANALYSIS_PATH, summary)

        current_status = project.get("status", "media_analyzed")
        self.manager.update_processing(
            root,
            current_status,
            media_library_path=MEDIA_LIBRARY_PATH,
            media_count=total,
            batch_visual_analysis_path=BATCH_VISUAL_ANALYSIS_PATH,
            batch_visual_analyzed=library.get("analyzed_count", 0),
        )
        stage(
            f"Análise em lote concluída: {library.get('analyzed_count', 0)}/{total} mídias prontas."
        )
        progress(100)
        return summary

    @staticmethod
    def _collect_candidates(target, asset, result):
        for scene in result.get("scenes", []):
            quality = scene.get("quality")
            if not isinstance(quality, dict):
                continue
            target.append(
                {
                    "asset_id": asset.get("id"),
                    "filename": asset.get("filename"),
                    "path": asset.get("path"),
                    "category_hint": asset.get("category_hint"),
                    "scene_id": scene.get("id"),
                    "start_ms": scene.get("start_ms"),
                    "end_ms": scene.get("end_ms"),
                    "duration_ms": scene.get("duration_ms"),
                    "score": quality.get("score", 0),
                    "quality_label": quality.get("label"),
                }
            )

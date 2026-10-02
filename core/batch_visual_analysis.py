from datetime import datetime, timezone
from pathlib import Path

from core.media_library import (
    MEDIA_LIBRARY_PATH,
    asset_from_path,
    load_media_library,
    save_media_library,
)
from core.processing import ProcessingCancelled, ProcessingError, check_cancelled
from core.project_manager import ProjectManager
from core.storage import read_json, write_json
from media.ffmpeg_tools import FFmpegTools
from media.motion_analyzer import MotionAnalyzer
from media.visual_analyzer import VisualAnalyzer


BATCH_VISUAL_ANALYSIS_PATH = "analysis/batch_visual_analysis.json"
MEDIA_ASSET_ANALYSIS_DIR = "analysis/media_assets"


def _quality_sample_budget(media_count):
    media_count = max(1, int(media_count))
    if media_count <= 4:
        return 10
    if media_count <= 12:
        return 5
    if media_count <= 40:
        return 3
    return 2


class BatchVisualAnalysisPipeline:
    def __init__(
        self,
        manager=None,
        tools=None,
        analyzer_factory=None,
        motion_analyzer_factory=None,
    ):
        self.manager = manager or ProjectManager()
        self.tools = tools or FFmpegTools()
        self.analyzer_factory = analyzer_factory
        self.motion_analyzer_factory = motion_analyzer_factory

    def _analyzer(self):
        if self.analyzer_factory is not None:
            return self.analyzer_factory()
        return VisualAnalyzer(self.tools.ffmpeg_path)

    def _motion_analyzer(self):
        if self.motion_analyzer_factory is not None:
            return self.motion_analyzer_factory()
        return MotionAnalyzer(self.tools.ffmpeg_path)

    def _run_motion_gate(
        self,
        root,
        asset,
        asset_path,
        visual_result,
        duration_ms,
        *,
        cancel=None,
        stage=lambda text: None,
        progress=lambda value: None,
    ):
        motion_result = self._motion_analyzer().analyze(
            asset_path,
            duration_ms,
            visual_result.get("scenes", []),
            cancel=cancel,
            stage=lambda text, name=asset_path.name: stage(f"{name} • {text}"),
            progress=progress,
        )
        asset_dir = root / MEDIA_ASSET_ANALYSIS_DIR / asset["id"]
        asset_dir.mkdir(parents=True, exist_ok=True)
        motion_path = asset_dir / "motion_analysis.json"
        write_json(motion_path, motion_result)
        asset["motion_analysis_path"] = str(motion_path.relative_to(root)).replace("\\", "/")
        asset["motion_gate_engine"] = motion_result.get("engine")
        asset["motion_trimmed_scenes"] = int(
            motion_result.get("trimmed_scene_count", 0) or 0
        )
        asset["motion_analysis_error"] = None
        return motion_result

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
        sample_budget = _quality_sample_budget(total)
        use_motion_gate = project.get("profile") == "Casamento"
        all_candidates = []
        reused = 0
        analyzed = 0
        failed = 0
        motion_assets = 0
        motion_trimmed_scenes = 0

        primary_path = Path(project["source"]["original_path"])
        if not primary_path.is_absolute():
            primary_path = root / primary_path
        primary_path = primary_path.resolve()
        primary_metadata = self.manager.load_media_metadata(root)

        for index, asset in enumerate(assets):
            check_cancelled(cancel)
            asset_path = Path(asset.get("path", ""))
            if not asset_path.exists():
                asset["analysis_status"] = "missing"
                asset["analysis_error"] = "Arquivo não encontrado."
                failed += 1
                continue

            fresh = asset_from_path(asset_path)
            if fresh["fingerprint"] != asset.get("fingerprint"):
                asset.update(fresh)

            base = int((index / total) * 100)
            span = max(1, int(100 / total))
            visual_rel = asset.get("visual_analysis_path")
            visual_path = root / visual_rel if visual_rel else None

            if (
                asset.get("analysis_status") == "complete"
                and visual_path is not None
                and visual_path.exists()
            ):
                try:
                    cached = read_json(visual_path)
                except (OSError, ValueError):
                    cached = None

                if isinstance(cached, dict):
                    motion_result = None
                    if use_motion_gate:
                        motion_rel = asset.get("motion_analysis_path")
                        motion_path = root / motion_rel if motion_rel else None
                        if motion_path is not None and motion_path.exists():
                            try:
                                motion_result = read_json(motion_path)
                            except (OSError, ValueError):
                                motion_result = None

                        if not isinstance(motion_result, dict):
                            seconds = asset.get("duration_seconds")
                            if isinstance(seconds, (int, float)) and seconds > 0:
                                try:
                                    motion_result = self._run_motion_gate(
                                        root,
                                        asset,
                                        asset_path,
                                        cached,
                                        int(round(seconds * 1000)),
                                        cancel=cancel,
                                        stage=stage,
                                        progress=lambda value, base=base, span=span: progress(
                                            min(
                                                99,
                                                base + int(
                                                    (max(0, min(100, value)) / 100)
                                                    * span
                                                ),
                                            )
                                        ),
                                    )
                                except ProcessingCancelled:
                                    raise
                                except Exception as error:
                                    asset["motion_analysis_error"] = str(error)
                                    motion_result = None

                        if isinstance(motion_result, dict):
                            motion_assets += 1
                            motion_trimmed_scenes += int(
                                motion_result.get("trimmed_scene_count", 0) or 0
                            )

                    reused += 1
                    self._collect_candidates(
                        all_candidates,
                        asset,
                        cached,
                        motion_result=motion_result,
                    )
                    save_media_library(root, library)
                    progress(int(((index + 1) / total) * 100))
                    continue

            stage(f"Analisando mídia {index + 1}/{total}: {asset_path.name}")

            try:
                if asset_path.resolve() == primary_path and primary_metadata is not None:
                    metadata = primary_metadata
                else:
                    metadata = self.tools.probe(asset_path, cancel=cancel)

                duration_seconds = metadata.get("container", {}).get("duration_seconds")
                if not isinstance(duration_seconds, (int, float)) or duration_seconds <= 0:
                    raise ProcessingError("Duração inválida para análise visual.")

                duration_ms = int(round(duration_seconds * 1000))
                analyzer = self._analyzer()
                visual_share = 0.72 if use_motion_gate else 1.0

                result = analyzer.analyze(
                    asset_path,
                    duration_ms,
                    cancel=cancel,
                    max_quality_samples=sample_budget,
                    stage=lambda text, name=asset_path.name: stage(f"{name} • {text}"),
                    progress=lambda value, base=base, span=span, share=visual_share: progress(
                        min(
                            99,
                            base
                            + int(
                                (max(0, min(100, value)) / 100)
                                * span
                                * share
                            ),
                        )
                    ),
                )

                asset_dir = root / MEDIA_ASSET_ANALYSIS_DIR / asset["id"]
                asset_dir.mkdir(parents=True, exist_ok=True)
                metadata_path = asset_dir / "metadata.json"
                visual_path = asset_dir / "visual_analysis.json"
                write_json(metadata_path, metadata)
                write_json(visual_path, result)

                motion_result = None
                if use_motion_gate:
                    try:
                        motion_result = self._run_motion_gate(
                            root,
                            asset,
                            asset_path,
                            result,
                            duration_ms,
                            cancel=cancel,
                            stage=stage,
                            progress=lambda value, base=base, span=span: progress(
                                min(
                                    99,
                                    base
                                    + int(
                                        span
                                        * (
                                            0.72
                                            + 0.28
                                            * (max(0, min(100, value)) / 100)
                                        )
                                    ),
                                )
                            ),
                        )
                        motion_assets += 1
                        motion_trimmed_scenes += int(
                            motion_result.get("trimmed_scene_count", 0) or 0
                        )
                    except ProcessingCancelled:
                        raise
                    except Exception as error:
                        # Motion Gate é melhoria de seleção, não pode invalidar
                        # uma análise visual que já terminou corretamente.
                        asset["motion_analysis_error"] = str(error)
                        motion_result = None

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
                        "audio_present": bool(metadata.get("audio", {}).get("present")),
                        "scene_count": summary.get("scene_count", 0),
                        "quality_average": summary.get("average_quality"),
                        "quality_samples": summary.get("quality_samples", 0),
                    }
                )
                analyzed += 1
                self._collect_candidates(
                    all_candidates,
                    asset,
                    result,
                    motion_result=motion_result,
                )
            except ProcessingCancelled:
                raise
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
            "schema_version": "0.4",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "media_count": total,
            "analyzed_now": analyzed,
            "reused_from_cache": reused,
            "failed": failed,
            "quality_samples_per_media": sample_budget,
            "total_scenes": sum(int(item.get("scene_count", 0) or 0) for item in assets),
            "motion_gate_engine": "motion-gate-v1" if use_motion_gate else None,
            "motion_gate_assets": motion_assets,
            "motion_trimmed_scenes": motion_trimmed_scenes,
            "best_take_candidates": all_candidates[:500],
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
            motion_gate_engine=summary.get("motion_gate_engine"),
            motion_trimmed_scenes=motion_trimmed_scenes,
        )
        stage(
            f"Análise em lote concluída: {library.get('analyzed_count', 0)}/{total} mídias prontas."
        )
        progress(100)
        return summary

    @staticmethod
    def _collect_candidates(target, asset, result, *, motion_result=None):
        motion_by_scene = {}
        if isinstance(motion_result, dict):
            motion_by_scene = {
                item.get("scene_id"): item
                for item in motion_result.get("scenes", [])
                if isinstance(item, dict)
            }

        for scene in result.get("scenes", []):
            quality = scene.get("quality")
            if not isinstance(quality, dict):
                continue

            motion = motion_by_scene.get(scene.get("id"), {})
            target.append(
                {
                    "asset_id": asset.get("id"),
                    "filename": asset.get("filename"),
                    "path": asset.get("path"),
                    "category_hint": asset.get("category_hint"),
                    "audio_present": asset.get("audio_present"),
                    "scene_id": scene.get("id"),
                    "start_ms": scene.get("start_ms"),
                    "end_ms": scene.get("end_ms"),
                    "duration_ms": scene.get("duration_ms"),
                    "score": quality.get("score", 0),
                    "quality_label": quality.get("label"),
                    "quality_sampled": quality.get("sampled"),
                    "motion_classification": motion.get("classification"),
                    "motion_confidence": motion.get("confidence", 0.0),
                    "motion_median": motion.get("median_motion"),
                    "motion_peak": motion.get("peak_motion"),
                    "motion_safe_start_ms": motion.get("safe_start_ms"),
                    "motion_safe_end_ms": motion.get("safe_end_ms"),
                    "motion_trim_start_ms": motion.get("trim_start_ms", 0),
                    "motion_trim_end_ms": motion.get("trim_end_ms", 0),
                }
            )

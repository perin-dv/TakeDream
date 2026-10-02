import tempfile
import unittest
from pathlib import Path

from core.project_manager import ProjectManager
from core.visual_analysis_pipeline import (
    QUALITY_SCORES_PATH,
    SCENE_ANALYSIS_PATH,
    VISUAL_ANALYSIS_PATH,
    VisualAnalysisPipeline,
)
from media.visual_analyzer import (
    VisualAnalyzer,
    build_scene_ranges,
    score_visual_sample,
)


class SceneDetectionTests(unittest.TestCase):
    def test_build_scene_ranges_from_cut_points(self):
        scenes = build_scene_ranges(
            [1500, 3200],
            5000,
        )

        self.assertEqual(len(scenes), 3)
        self.assertEqual(scenes[0]["start_ms"], 0)
        self.assertEqual(scenes[0]["end_ms"], 1500)
        self.assertEqual(scenes[-1]["end_ms"], 5000)

    def test_tiny_scene_is_merged(self):
        scenes = build_scene_ranges(
            [100, 1600],
            3000,
            minimum_scene_ms=250,
        )

        self.assertEqual(
            [scene["start_ms"] for scene in scenes],
            [0, 1600],
        )

    def test_ffmpeg_showinfo_is_parsed_into_scene_changes(self):
        def fake_runner(command, cancel=None, timeout=None):
            return "", (
                "[Parsed_showinfo_1] n:0 pts:1 pts_time:1.250 pos:0\n"
                "[Parsed_showinfo_1] n:1 pts:2 pts_time:3.750 pos:0\n"
            )

        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "video.mp4"
            source.write_bytes(b"fake")
            analyzer = VisualAnalyzer("ffmpeg", runner=fake_runner)
            cuts = analyzer.detect_scene_changes(
                source,
                5000,
            )

        self.assertEqual(cuts, [1250, 3750])

    def test_quality_metadata_is_parsed_from_ffmpeg_output(self):
        def fake_runner(command, cancel=None, timeout=None):
            return (
                "lavfi.signalstats.YAVG=112.25\n",
                "[Parsed_blurdetect_3] blur mean: 0.120000\n",
            )

        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "video.mp4"
            source.write_bytes(b"fake")
            result = VisualAnalyzer(
                "ffmpeg",
                runner=fake_runner,
            ).sample_quality(
                source,
                1000,
                2500,
            )

        self.assertEqual(result["yavg"], 112.25)
        self.assertEqual(result["blur"], 0.12)
        self.assertGreater(result["score"], 70)


class QualityScoringTests(unittest.TestCase):
    def test_good_frame_scores_above_bad_frame(self):
        good = score_visual_sample(
            yavg=110,
            blur=0.10,
            duration_ms=2500,
        )
        bad = score_visual_sample(
            yavg=30,
            blur=0.80,
            duration_ms=500,
        )

        self.assertGreater(good["score"], bad["score"])
        self.assertIn(good["label"], ("excelente", "boa"))

    def test_missing_metrics_degrades_safely(self):
        score = score_visual_sample(
            yavg=None,
            blur=None,
            duration_ms=1000,
        )

        self.assertGreater(score["score"], 0)
        self.assertIsNone(score["yavg"])
        self.assertIsNone(score["blur"])


class VisualAnalysisPipelineTests(unittest.TestCase):
    def test_pipeline_persists_scene_and_quality_files_without_regressing_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "video.mp4"
            source.write_bytes(b"fake")

            manager = ProjectManager(root / "projects")
            project = manager.create_project(
                "Casamento",
                source,
                "Casamento",
                "Highlight",
            )
            manager.update_processing(project, "transcribed")

            metadata = {
                "container": {"duration_seconds": 5.0},
                "video": {"width": 1920, "height": 1080},
                "audio": {"present": True},
            }

            class FakeTools:
                ffmpeg_path = "ffmpeg"

                def probe(self, path, cancel=None):
                    return metadata

            class FakeAnalyzer:
                def analyze(self, source, duration_ms, **kwargs):
                    return {
                        "schema_version": "0.1",
                        "scene_threshold": 0.30,
                        "scenes": [
                            {
                                "id": 0,
                                "start_ms": 0,
                                "end_ms": 2500,
                                "duration_ms": 2500,
                                "sample_ms": 1250,
                                "quality": {
                                    "score": 91.0,
                                    "label": "excelente",
                                },
                            },
                            {
                                "id": 1,
                                "start_ms": 2500,
                                "end_ms": 5000,
                                "duration_ms": 2500,
                                "sample_ms": 3750,
                                "quality": {
                                    "score": 74.0,
                                    "label": "boa",
                                },
                            },
                        ],
                        "summary": {
                            "scene_count": 2,
                            "quality_samples": 2,
                            "average_quality": 82.5,
                            "best_scene_ids": [0, 1],
                        },
                    }

            result = VisualAnalysisPipeline(
                manager=manager,
                tools=FakeTools(),
                analyzer=FakeAnalyzer(),
            ).run(project, metadata=metadata)

            self.assertEqual(result["summary"]["scene_count"], 2)
            self.assertTrue((project / VISUAL_ANALYSIS_PATH).exists())
            self.assertTrue((project / SCENE_ANALYSIS_PATH).exists())
            self.assertTrue((project / QUALITY_SCORES_PATH).exists())
            _, data = manager.load_project(project)
            self.assertEqual(data["status"], "transcribed")
            self.assertEqual(data["visual_scene_count"], 2)
            self.assertEqual(data["visual_quality_average"], 82.5)


if __name__ == "__main__":
    unittest.main()

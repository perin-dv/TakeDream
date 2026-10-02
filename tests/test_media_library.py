import tempfile
import unittest
from pathlib import Path

from core.batch_visual_analysis import BatchVisualAnalysisPipeline
from core.deliverables import build_wedding_story_budget, normalize_deliverable
from core.media_library import discover_media, load_media_library
from core.project_manager import ProjectManager


class DeliverableTests(unittest.TestCase):
    def test_wedding_trailer_has_independent_story_target(self):
        value = normalize_deliverable("Casamento", "trailer", 240)
        self.assertEqual(value["type"], "trailer")
        self.assertEqual(value["target_seconds"], 240)
        self.assertEqual(value["pacing"], "cinematográfico")
        self.assertEqual(value["selection_strategy"], "narrative_highlight")
        self.assertFalse(value["preserve_long_form"])

    def test_wedding_film_preserves_long_form(self):
        value = normalize_deliverable("Casamento", "film", 1500)
        self.assertTrue(value["preserve_long_form"])
        self.assertEqual(value["target_seconds"], 1500)
        self.assertEqual(value["selection_strategy"], "long_form_story")

    def test_teaser_and_film_use_different_story_budgets(self):
        teaser = build_wedding_story_budget("teaser", 60)
        film = build_wedding_story_budget("film", 1200)

        self.assertGreater(
            teaser["sections"]["festa"] / teaser["target_seconds"],
            film["sections"]["festa"] / film["target_seconds"],
        )
        self.assertGreater(
            film["sections"]["cerimonia"] / film["target_seconds"],
            teaser["sections"]["cerimonia"] / teaser["target_seconds"],
        )
        self.assertGreater(film["voice_seconds"], teaser["voice_seconds"])
        self.assertGreater(film["average_shot_seconds"], teaser["average_shot_seconds"])

    def test_invalid_teaser_duration_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_deliverable("Casamento", "teaser", 600)


class MediaLibraryTests(unittest.TestCase):
    def test_discovers_multiple_videos_from_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "cam1").mkdir()
            (root / "drone").mkdir()
            (root / "cam1" / "A001.mp4").write_bytes(b"a")
            (root / "drone" / "D001.mov").write_bytes(b"b")
            (root / "notes.txt").write_text("ignore", encoding="utf-8")

            media = discover_media([root])
            self.assertEqual(len(media), 2)
            self.assertEqual({item.suffix for item in media}, {".mp4", ".mov"})

    def test_project_keeps_primary_source_and_media_library(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            a = root / "A001.mp4"
            b = root / "B001.mp4"
            a.write_bytes(b"a")
            b.write_bytes(b"b")

            manager = ProjectManager(root / "projects")
            project = manager.create_project(
                "Casamento lote",
                a,
                "Casamento",
                "Highlight",
                source_videos=[b],
                deliverable_type="trailer",
                target_duration_seconds=240,
            )

            _, data = manager.load_project(project)
            library = load_media_library(project)
            self.assertEqual(data["media_count"], 2)
            self.assertEqual(data["deliverable_type"], "trailer")
            self.assertEqual(data["target_duration_seconds"], 240)
            self.assertEqual(library["media_count"], 2)
            self.assertEqual(data["source"]["filename"], "A001.mp4")

    def test_adding_media_does_not_regress_project_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            a = root / "A.mp4"
            b = root / "B.mp4"
            a.write_bytes(b"a")
            b.write_bytes(b"b")
            manager = ProjectManager(root / "projects")
            project = manager.create_project("Lote", a, "YouTube", "Clean")
            manager.update_processing(project, "transcribed")

            library = manager.add_media_sources(project, [b])
            _, data = manager.load_project(project)
            self.assertEqual(library["media_count"], 2)
            self.assertEqual(data["status"], "transcribed")


class BatchVisualAnalysisTests(unittest.TestCase):
    def test_batch_analysis_reuses_cached_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            a = root / "A.mp4"
            b = root / "B.mp4"
            a.write_bytes(b"a")
            b.write_bytes(b"b")
            manager = ProjectManager(root / "projects")
            project = manager.create_project(
                "Wedding",
                a,
                "Casamento",
                "Highlight",
                source_videos=[b],
            )

            class FakeTools:
                ffmpeg_path = "ffmpeg"

                def probe(self, path, cancel=None):
                    return {
                        "container": {"duration_seconds": 10.0},
                        "video": {"resolution": "1920x1080", "fps": 30.0},
                        "audio": {"present": True},
                    }

            calls = []

            class FakeAnalyzer:
                def analyze(self, source, duration_ms, **kwargs):
                    calls.append(Path(source).name)
                    return {
                        "schema_version": "0.1",
                        "scenes": [
                            {
                                "id": 0,
                                "start_ms": 0,
                                "end_ms": duration_ms,
                                "duration_ms": duration_ms,
                                "quality": {"score": 88.0, "label": "boa"},
                            }
                        ],
                        "summary": {
                            "scene_count": 1,
                            "average_quality": 88.0,
                        },
                    }

            pipeline = BatchVisualAnalysisPipeline(
                manager=manager,
                tools=FakeTools(),
                analyzer_factory=lambda: FakeAnalyzer(),
            )
            first = pipeline.run(project)
            second = pipeline.run(project)

            self.assertEqual(first["analyzed_now"], 2)
            self.assertEqual(second["analyzed_now"], 0)
            self.assertEqual(second["reused_from_cache"], 2)
            self.assertEqual(len(calls), 2)
            self.assertEqual(len(second["best_take_candidates"]), 2)


if __name__ == "__main__":
    unittest.main()

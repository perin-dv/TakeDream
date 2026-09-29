import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.ui.wedding_setup import WeddingSetupWidget
from app.windows.new_project_dialog import NewProjectDialog
from core.project_manager import ProjectManager
from core.wedding_assembly import build_wedding_assembly_plan
from renderer.multisource_renderer import MultiSourceRenderer


class WeddingSetupUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_wedding_project_data_contains_delivery_reference_and_music(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "C001.mp4"
            reference = root / "modelo.mp4"
            music = root / "trilha.mp3"
            for path in (source, reference, music):
                path.write_bytes(b"x")

            dialog = NewProjectDialog()
            try:
                dialog._add_media_paths([source])
                dialog._set_profile("Casamento")
                dialog.wedding_setup.set_deliverable("teaser")
                dialog.wedding_setup.reference_video_path = str(reference.resolve())
                dialog.wedding_setup.music_path = str(music.resolve())
                data = dialog.project_data()

                self.assertEqual(data["profile"], "Casamento")
                self.assertEqual(data["deliverable_type"], "teaser")
                self.assertEqual(data["target_duration_seconds"], 60)
                self.assertEqual(data["reference_video"], str(reference.resolve()))
                self.assertEqual(data["music_path"], str(music.resolve()))
            finally:
                dialog.close()

    def test_duration_widget_formats_minutes(self):
        widget = WeddingSetupWidget()
        try:
            widget.set_deliverable("trailer")
            self.assertEqual(widget.duration_spin.value(), 210)
            self.assertEqual(widget.duration_spin.textFromValue(210), "3m 30s")
        finally:
            widget.close()


class WeddingProjectPersistenceTests(unittest.TestCase):
    def test_manager_persists_reference_and_music_without_adding_them_to_media_bin(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_a = root / "C001.mp4"
            source_b = root / "C002.mp4"
            reference = root / "modelo.mp4"
            music = root / "trilha.mp3"
            for path in (source_a, source_b, reference, music):
                path.write_bytes(b"x")

            manager = ProjectManager(root / "projects")
            project_dir = manager.create_project(
                "Wedding reference",
                source_a,
                "Casamento",
                "Highlight",
                source_videos=[source_b],
                deliverable_type="trailer",
                target_duration_seconds=240,
                reference_video=reference,
                music_path=music,
            )
            _, project = manager.load_project(project_dir)
            library = manager.load_media_library(project_dir)

            self.assertEqual(project["target_duration_seconds"], 240)
            self.assertEqual(project["reference_video_path"], str(reference.resolve()))
            self.assertEqual(project["music_source_path"], str(music.resolve()))
            self.assertTrue(project["wedding_setup"]["reference_enabled"])
            self.assertTrue(project["wedding_setup"]["music_enabled"])
            self.assertEqual(library["media_count"], 2)


class ReferenceDrivenAssemblyTests(unittest.TestCase):
    def test_reference_timing_changes_rough_cut_shot_lengths(self):
        assets = []
        candidates = []
        for index in range(6):
            asset_id = f"a{index}"
            path = f"C{index}.mp4"
            assets.append({"id": asset_id, "path": path, "category_hint": "casal"})
            candidates.append(
                {
                    "asset_id": asset_id,
                    "path": path,
                    "filename": path,
                    "category_hint": "casal",
                    "scene_id": 0,
                    "start_ms": 0,
                    "end_ms": 10000,
                    "duration_ms": 10000,
                    "score": 90 - index,
                }
            )

        project = {
            "profile": "Casamento",
            "style": "Highlight",
            "deliverable": {
                "type": "teaser",
                "target_seconds": 10,
                "average_shot_seconds": 1.5,
                "preserve_long_form": False,
            },
            "review_settings": {"auto_zoom": False},
        }
        timing = {
            "reference_rhythm": "rapido",
            "music_snap_enabled": True,
            "shots": [
                {"duration_ms": 1000},
                {"duration_ms": 1500},
                {"duration_ms": 2000},
                {"duration_ms": 2500},
                {"duration_ms": 3000},
            ],
        }
        plan = build_wedding_assembly_plan(
            project,
            {"assets": assets},
            {"best_take_candidates": candidates},
            reference_timing=timing,
        )

        self.assertTrue(plan["reference_timing_applied"])
        self.assertTrue(plan["music_snap_enabled"])
        self.assertEqual(
            [clip["duration_ms"] for clip in plan["clips"][:4]],
            [1000, 1500, 2000, 2500],
        )


class MultiSourceMusicGraphTests(unittest.TestCase):
    def test_music_is_mixed_under_source_audio(self):
        renderer = MultiSourceRenderer(None)
        clips = [
            {"duration_ms": 2000, "zoom_scale": 1.0},
            {"duration_ms": 3000, "zoom_scale": 1.0},
        ]
        graph = renderer._build_graph(
            clips,
            1920,
            1080,
            [True, True],
            None,
            music_path="trilha.mp3",
        )

        self.assertIn("[2:a:0]", graph)
        self.assertIn("amix=inputs=2", graph)
        self.assertIn("volume=0.30", graph)
        self.assertIn("[outa]", graph)


if __name__ == "__main__":
    unittest.main()

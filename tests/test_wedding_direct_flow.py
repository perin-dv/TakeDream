import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.processing_worker import ProcessingWorker
from core.project_manager import ProjectManager
from core.wedding_assembly import build_wedding_assembly_plan
from renderer.multisource_renderer import MultiSourceRenderer


class WeddingDirectFlowTests(unittest.TestCase):
    def test_load_auto_starts_wedding_multimedia_pipeline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "C001.mp4"
            second = root / "C002.mp4"
            first.write_bytes(b"a")
            second.write_bytes(b"b")

            manager = ProjectManager(root / "projects")
            project = manager.create_project(
                "Casamento direto",
                first,
                "Casamento",
                "Highlight",
                source_videos=[second],
                deliverable_type="trailer",
                target_duration_seconds=210,
            )

            completed = []
            worker = ProcessingWorker(project, "load")
            worker.completed.connect(completed.append)

            with patch(
                "app.processing_worker.AutoEditPipeline.run",
                return_value={
                    "output_path": "output/wedding_assembly_base.mp4",
                    "edit_plan": None,
                    "errors": [],
                    "edit_errors": [],
                },
            ) as run:
                worker.run()

            run.assert_called_once()
            self.assertTrue(completed)
            self.assertTrue(completed[0]["auto_pipeline"])

    def test_reference_rhythm_does_not_limit_new_wedding_to_reference_shot_count(self):
        assets = []
        candidates = []
        for index in range(12):
            asset_id = f"asset-{index}"
            path = f"C{index:04d}.mp4"
            assets.append(
                {
                    "id": asset_id,
                    "path": path,
                    "filename": path,
                    "category_hint": "nao_classificado",
                    "duration_seconds": 26.0,
                    "audio_present": True,
                }
            )
            candidates.append(
                {
                    "asset_id": asset_id,
                    "path": path,
                    "filename": path,
                    "category_hint": "nao_classificado",
                    "audio_present": True,
                    "scene_id": 0,
                    "start_ms": 0,
                    "end_ms": 26000,
                    "duration_ms": 26000,
                    "score": 90 - index,
                }
            )

        project = {
            "profile": "Casamento",
            "style": "Highlight",
            "music_source_path": "nova-musica.mp3",
            "deliverable": {
                "type": "trailer",
                "target_seconds": 210,
                "average_shot_seconds": 2.6,
                "preserve_long_form": False,
            },
            "review_settings": {"auto_zoom": False},
        }
        reference_timing = {
            "reference_rhythm": "moderado",
            "music_snap_enabled": True,
            "shots": [
                {"duration_ms": 26000},
                {"duration_ms": 26000},
                {"duration_ms": 26000},
            ],
        }

        plan = build_wedding_assembly_plan(
            project,
            {"assets": assets},
            {"best_take_candidates": candidates},
            reference_timing=reference_timing,
        )

        self.assertGreater(plan["clip_count"], 3)
        self.assertGreaterEqual(plan["estimated_duration_ms"], 180000)
        self.assertLessEqual(plan["estimated_duration_ms"], 210000)
        self.assertFalse(plan["reference_audio_used"])

    def test_music_mutes_broll_source_audio_but_keeps_vows(self):
        assets = [
            {"id": "v", "path": "VOTOS/v.mp4", "category_hint": "votos_falas"},
            {"id": "f", "path": "FESTA/f.mp4", "category_hint": "festa"},
        ]
        candidates = [
            {
                "asset_id": "v",
                "path": "VOTOS/v.mp4",
                "filename": "v.mp4",
                "category_hint": "votos_falas",
                "scene_id": 0,
                "start_ms": 0,
                "end_ms": 8000,
                "duration_ms": 8000,
                "score": 90,
                "audio_present": True,
            },
            {
                "asset_id": "f",
                "path": "FESTA/f.mp4",
                "filename": "f.mp4",
                "category_hint": "festa",
                "scene_id": 0,
                "start_ms": 0,
                "end_ms": 8000,
                "duration_ms": 8000,
                "score": 88,
                "audio_present": True,
            },
        ]
        project = {
            "profile": "Casamento",
            "style": "Highlight",
            "music_source_path": "trilha.mp3",
            "deliverable": {
                "type": "teaser",
                "target_seconds": 12,
                "average_shot_seconds": 2.0,
                "preserve_long_form": False,
            },
            "review_settings": {"auto_zoom": False},
        }

        plan = build_wedding_assembly_plan(
            project,
            {"assets": assets},
            {"best_take_candidates": candidates},
        )
        by_section = {clip["story_section"]: clip for clip in plan["clips"]}

        self.assertEqual(by_section["votos_falas"]["source_audio_gain"], 1.0)
        self.assertEqual(by_section["festa"]["source_audio_gain"], 0.0)
        self.assertEqual(plan["source_audio_policy"], "dialogue_only_with_music")

    def test_renderer_uses_silence_for_muted_source_audio(self):
        renderer = MultiSourceRenderer(None)
        graph = renderer._build_graph(
            [
                {"duration_ms": 2000, "zoom_scale": 1.0, "source_audio_gain": 0.0},
                {"duration_ms": 2000, "zoom_scale": 1.0, "source_audio_gain": 1.0},
            ],
            1920,
            1080,
            [True, True],
            None,
            music_path="trilha.mp3",
        )

        self.assertIn("anullsrc=r=48000:cl=stereo:d=2.000000[a0]", graph)
        self.assertIn("volume=1.000[a1]", graph)
        self.assertIn("sidechaincompress", graph)


if __name__ == "__main__":
    unittest.main()

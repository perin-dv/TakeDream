import tempfile
import unittest
from pathlib import Path

from core.batch_visual_analysis import _quality_sample_budget
from core.project_manager import ProjectManager
from core.render_effects import zoom_events_for_settings
from core.wedding_assembly import build_wedding_assembly_plan


class WeddingAssemblyPlanTests(unittest.TestCase):
    def test_eight_short_videos_do_not_collapse_to_first_26_seconds(self):
        assets = []
        candidates = []
        for index in range(8):
            asset_id = f"asset-{index}"
            path = f"C{index:04d}.MP4"
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
                    "score": 80.0 - index,
                    "quality_label": "boa",
                }
            )

        project = {
            "profile": "Casamento",
            "style": "Highlight",
            "deliverable": {
                "type": "trailer",
                "label": "Trailer / Highlight",
                "target_seconds": 210,
                "minimum_seconds": 150,
                "maximum_seconds": 300,
                "pacing": "cinematográfico",
                "voice_ratio": 0.28,
                "average_shot_seconds": 2.6,
                "preserve_long_form": False,
                "description": "teste",
            },
            "review_settings": {"auto_zoom": False},
        }
        library = {"assets": assets}
        summary = {"best_take_candidates": candidates}

        plan = build_wedding_assembly_plan(project, library, summary)

        self.assertEqual(plan["media_count"], 8)
        self.assertEqual(plan["clip_count"], 8)
        self.assertGreater(plan["estimated_duration_ms"], 180000)
        self.assertLessEqual(plan["estimated_duration_ms"], 210000)

    def test_explicit_zoom_toggle_overrides_conservative_wedding_preset(self):
        project = {
            "profile": "Casamento",
            "style": "Highlight",
            "deliverable": {
                "type": "trailer",
                "target_seconds": 60,
                "average_shot_seconds": 2.6,
                "preserve_long_form": False,
            },
            "review_settings": {"auto_zoom": True},
        }
        library = {
            "assets": [
                {
                    "id": "a",
                    "path": "a.mp4",
                    "filename": "a.mp4",
                    "category_hint": "casal",
                },
                {
                    "id": "b",
                    "path": "b.mp4",
                    "filename": "b.mp4",
                    "category_hint": "festa",
                },
            ]
        }
        summary = {
            "best_take_candidates": [
                {
                    "asset_id": "a",
                    "path": "a.mp4",
                    "filename": "a.mp4",
                    "category_hint": "casal",
                    "scene_id": 0,
                    "start_ms": 0,
                    "end_ms": 30000,
                    "duration_ms": 30000,
                    "score": 90,
                },
                {
                    "asset_id": "b",
                    "path": "b.mp4",
                    "filename": "b.mp4",
                    "category_hint": "festa",
                    "scene_id": 0,
                    "start_ms": 0,
                    "end_ms": 30000,
                    "duration_ms": 30000,
                    "score": 88,
                },
            ]
        }

        plan = build_wedding_assembly_plan(project, library, summary)
        self.assertTrue(any(clip["zoom_scale"] > 1.0 for clip in plan["clips"]))


class ZoomFallbackTests(unittest.TestCase):
    def test_review_zoom_generates_events_even_without_semantic_suggestions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.mp4"
            source.write_bytes(b"fake")
            manager = ProjectManager(root / "projects")
            project = manager.create_project(
                "Wedding zoom",
                source,
                "Casamento",
                "Highlight",
            )
            manager.update_processing(
                project,
                "rendered",
                wedding_assembly_duration_ms=60000,
            )

            events = zoom_events_for_settings(project, {"auto_zoom": True})
            self.assertGreater(len(events), 0)
            self.assertGreater(events[0]["scale"], 1.0)


class BatchBudgetTests(unittest.TestCase):
    def test_quality_budget_scales_down_for_media_bin(self):
        self.assertEqual(_quality_sample_budget(8), 5)
        self.assertEqual(_quality_sample_budget(25), 3)
        self.assertEqual(_quality_sample_budget(200), 2)


if __name__ == "__main__":
    unittest.main()

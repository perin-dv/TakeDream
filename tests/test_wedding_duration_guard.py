import unittest

from core.wedding_assembly import build_wedding_assembly_plan


class WeddingDurationGuardTests(unittest.TestCase):
    def test_many_low_priority_takes_still_fill_trailer_when_material_exists(self):
        assets = []
        candidates = []
        for index in range(50):
            asset_id = f"asset-{index:02d}"
            path = f"MVI_{index:04d}.MP4"
            assets.append(
                {
                    "id": asset_id,
                    "path": path,
                    "filename": path,
                    "category_hint": "nao_classificado",
                    "duration_seconds": 5.0,
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
                    "end_ms": 5000,
                    "duration_ms": 5000,
                    "score": 44.0,
                    "quality_label": "fraca",
                    "quality_sampled": True,
                }
            )

        project = {
            "profile": "Casamento",
            "style": "Highlight",
            "deliverable": {
                "type": "trailer",
                "label": "Trailer / Highlight",
                "target_seconds": 180,
                "minimum_seconds": 150,
                "maximum_seconds": 300,
                "pacing": "cinematografico",
                "voice_ratio": 0.28,
                "average_shot_seconds": 2.6,
                "preserve_long_form": False,
                "description": "teste",
            },
            "review_settings": {"auto_zoom": False},
        }
        library = {"assets": assets}
        summary = {"best_take_candidates": candidates}
        reference_timing = {
            "reference_rhythm": "rapido",
            "shots": [
                {"duration_ms": 1000},
                {"duration_ms": 1200},
                {"duration_ms": 900},
                {"duration_ms": 1400},
            ],
        }

        plan = build_wedding_assembly_plan(
            project,
            library,
            summary,
            reference_timing=reference_timing,
        )

        self.assertGreaterEqual(plan["estimated_duration_ms"], 170000)
        self.assertLessEqual(plan["estimated_duration_ms"], 180000)
        self.assertGreater(plan["clip_count"], 20)
        self.assertGreater(plan["media_count"], 20)
        self.assertLess(plan["duration_shortfall_ms"], 10000)


if __name__ == "__main__":
    unittest.main()

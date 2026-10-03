import unittest

from core.best_shot_selector import (
    candidate_selection_score,
    is_usable_wedding_candidate,
    per_asset_limit,
    rank_wedding_candidates,
    source_too_close,
)
from core.wedding_story import build_story_candidate_plan


class BestShotSelectorTests(unittest.TestCase):
    def test_semantic_confidence_can_break_close_quality_tie(self):
        strong_semantic = {
            "asset_id": "a",
            "score": 84,
            "semantic_confidence": 0.95,
            "duration_ms": 3000,
            "quality_sampled": True,
        }
        plain = {
            "asset_id": "b",
            "score": 86,
            "semantic_confidence": 0.0,
            "duration_ms": 3000,
            "quality_sampled": True,
        }
        self.assertGreater(
            candidate_selection_score(strong_semantic),
            candidate_selection_score(plain),
        )
        ranked = rank_wedding_candidates([plain, strong_semantic])
        self.assertEqual(ranked[0]["asset_id"], "a")

    def test_ground_or_reposition_composition_is_rejected(self):
        candidate = {
            "asset_id": "floor",
            "score": 92,
            "duration_ms": 3200,
            "quality_label": "excelente",
            "quality_sampled": True,
            "visual_semantics": {
                "quality": {
                    "whip_score": 0.08,
                    "shake_score": 0.12,
                    "motion_blur_score": 0.10,
                    "composition_risk_score": 0.78,
                    "accidental_floor_score": 0.78,
                }
            },
        }
        self.assertFalse(is_usable_wedding_candidate(candidate))

    def test_internal_whip_is_rejected_even_when_frame_is_sharp(self):
        candidate = {
            "asset_id": "whip",
            "score": 94,
            "duration_ms": 4000,
            "quality_label": "excelente",
            "quality_sampled": True,
            "motion_classification": "internal_whip",
            "motion_confidence": 0.72,
        }
        self.assertFalse(is_usable_wedding_candidate(candidate))

    def test_nearby_scenes_from_same_source_are_considered_too_close(self):
        candidate = {
            "asset_id": "camera-a",
            "start_ms": 5000,
            "end_ms": 8000,
        }
        selected = [
            {
                "asset_id": "camera-a",
                "start_ms": 8200,
                "end_ms": 11000,
            }
        ]
        self.assertTrue(source_too_close(candidate, selected, minimum_gap_ms=1200))
        self.assertFalse(
            source_too_close(
                {"asset_id": "camera-b", "start_ms": 5000, "end_ms": 8000},
                selected,
                minimum_gap_ms=1200,
            )
        )

    def test_limits_are_stricter_for_teaser_than_full_film(self):
        self.assertLess(per_asset_limit("teaser"), per_asset_limit("trailer"))
        self.assertLess(per_asset_limit("trailer"), per_asset_limit("film"))

    def test_story_builder_prefers_media_diversity(self):
        assets = [
            {"id": "a"},
            {"id": "b"},
            {"id": "c"},
        ]
        candidates = []
        for asset_index, asset_id in enumerate(("a", "b", "c")):
            for scene in range(4):
                start = scene * 5000
                candidates.append(
                    {
                        "asset_id": asset_id,
                        "scene_id": scene,
                        "path": f"CASAL/{asset_id}-{scene}.mp4",
                        "filename": f"{asset_id}-{scene}.mp4",
                        "category_hint": "casal",
                        "start_ms": start,
                        "end_ms": start + 3000,
                        "duration_ms": 3000,
                        "score": 95 - asset_index - scene,
                    }
                )

        deliverable = {
            "type": "teaser",
            "story_budget": {
                "sections": {
                    "making_of": 0,
                    "cerimonia": 0,
                    "votos_falas": 0,
                    "casal": 30,
                    "recepcao": 0,
                    "festa": 0,
                    "finale": 0,
                }
            },
        }
        result = build_story_candidate_plan(
            candidates,
            assets,
            deliverable,
            target_ms=30000,
            base_clip_ms=3000,
            max_clips=10,
        )
        selected = result["selected_candidates"]
        first_three_assets = {item["asset_id"] for item in selected[:3]}
        self.assertEqual(first_three_assets, {"a", "b", "c"})
        self.assertEqual(result["best_shot_engine"], "best-shot-selector-v2")


if __name__ == "__main__":
    unittest.main()

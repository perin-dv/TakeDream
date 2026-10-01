import unittest

from core.deliverables import normalize_deliverable
from core.wedding_assembly import build_wedding_assembly_plan


class WeddingStoryAssemblyIntegrationTests(unittest.TestCase):
    def test_assembly_exposes_story_sections_and_orders_clips(self):
        deliverable = normalize_deliverable("Casamento", "trailer", 150)
        project = {
            "profile": "Casamento",
            "style": "Highlight",
            "deliverable": deliverable,
            "review_settings": {"auto_zoom": False},
        }

        specs = [
            ("m1", "MAKING NOIVA", 91),
            ("c1", "CERIMONIA", 89),
            ("v1", "VOTOS", 95),
            ("p1", "CASAL EXTERNA", 90),
            ("r1", "RECEPCAO", 84),
            ("f1", "FESTA DJ", 93),
            ("z1", "SAIDA DOS NOIVOS", 86),
        ]
        assets = []
        candidates = []
        for index, (asset_id, folder, score) in enumerate(specs):
            path = f"/CASAMENTO/{folder}/{asset_id}.mp4"
            assets.append(
                {
                    "id": asset_id,
                    "path": path,
                    "filename": f"{asset_id}.mp4",
                    "duration_seconds": 30.0,
                    "category_hint": "nao_classificado",
                    "audio_present": True,
                }
            )
            candidates.append(
                {
                    "asset_id": asset_id,
                    "path": path,
                    "filename": f"{asset_id}.mp4",
                    "category_hint": "nao_classificado",
                    "audio_present": True,
                    "scene_id": index,
                    "start_ms": 0,
                    "end_ms": 30000,
                    "duration_ms": 30000,
                    "score": score,
                }
            )

        plan = build_wedding_assembly_plan(
            project,
            {"assets": assets},
            {"best_take_candidates": candidates},
        )

        self.assertTrue(plan["story_builder_applied"])
        self.assertEqual(plan["story_builder"], "wedding-story-builder-v1")
        self.assertTrue(plan["story_sections"])

        order = {name: index for index, name in enumerate(plan["story_order"])}
        clip_order = [
            order.get(clip["story_section"], 99)
            for clip in plan["clips"]
            if clip["story_section"] in order
        ]
        self.assertEqual(clip_order, sorted(clip_order))

        actual_total = sum(
            section.get("actual_ms", 0)
            for section in plan["story_sections"]
        )
        self.assertEqual(actual_total, plan["estimated_duration_ms"])
        self.assertTrue(
            any(section["key"] == "votos_falas" for section in plan["story_sections"])
        )


if __name__ == "__main__":
    unittest.main()

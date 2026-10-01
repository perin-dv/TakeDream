import unittest

from core.deliverables import normalize_deliverable
from core.wedding_story import (
    build_story_candidate_plan,
    classify_story_section,
)


class WeddingStoryClassificationTests(unittest.TestCase):
    def test_classifies_common_wedding_folders(self):
        self.assertEqual(
            classify_story_section({"path": "CASAMENTO/MAKING NOIVA/C001.mp4"}),
            "making_of",
        )
        self.assertEqual(
            classify_story_section({"path": "CASAMENTO/CERIMONIA/VOTOS/C010.mp4"}),
            "votos_falas",
        )
        self.assertEqual(
            classify_story_section({"path": "CASAMENTO/CASAL/EXTERNA/C020.mp4"}),
            "casal",
        )
        self.assertEqual(
            classify_story_section({"path": "CASAMENTO/FESTA/DJ/C030.mp4"}),
            "festa",
        )


class WeddingStoryPlanTests(unittest.TestCase):
    def _candidate(self, asset_id, section, score=80, start=0, duration=12000):
        names = {
            "making_of": "making noiva",
            "cerimonia": "cerimonia",
            "votos_falas": "votos",
            "casal": "casal externa",
            "recepcao": "recepcao",
            "festa": "festa dj",
            "finale": "saida dos noivos",
        }
        return {
            "asset_id": asset_id,
            "scene_id": 0,
            "path": f"/{names[section]}/{asset_id}.mp4",
            "filename": f"{asset_id}.mp4",
            "start_ms": start,
            "end_ms": start + duration,
            "duration_ms": duration,
            "score": score,
        }

    def test_trailer_builds_ordered_story_sections(self):
        deliverable = normalize_deliverable("Casamento", "trailer", 180)
        candidates = [
            self._candidate("a", "festa", 90),
            self._candidate("b", "making_of", 85),
            self._candidate("c", "cerimonia", 88),
            self._candidate("d", "votos_falas", 92),
            self._candidate("e", "casal", 87),
            self._candidate("f", "recepcao", 82),
            self._candidate("g", "finale", 84),
        ]
        assets = [{"id": item["asset_id"]} for item in candidates]

        story = build_story_candidate_plan(
            candidates,
            assets,
            deliverable,
            target_ms=180000,
            base_clip_ms=5000,
            max_clips=50,
        )

        sections = [item["story_section"] for item in story["selected_candidates"]]
        order = {name: index for index, name in enumerate(story["story_order"])}
        numeric = [order.get(name, 99) for name in sections if name in order]
        self.assertEqual(numeric, sorted(numeric))
        self.assertIn("votos_falas", sections)
        self.assertIn("festa", sections)
        self.assertGreater(story["classified_candidates"], 0)

    def test_unclassified_media_is_not_discarded(self):
        deliverable = normalize_deliverable("Casamento", "trailer", 150)
        candidates = []
        assets = []
        for index in range(8):
            asset_id = f"asset-{index}"
            assets.append({"id": asset_id})
            candidates.append(
                {
                    "asset_id": asset_id,
                    "scene_id": 0,
                    "path": f"/camera/C{index:03d}.mp4",
                    "filename": f"C{index:03d}.mp4",
                    "start_ms": 0,
                    "end_ms": 26000,
                    "duration_ms": 26000,
                    "score": 90 - index,
                }
            )

        story = build_story_candidate_plan(
            candidates,
            assets,
            deliverable,
            target_ms=150000,
            base_clip_ms=5000,
            max_clips=50,
        )

        selected_assets = {
            item["asset_id"] for item in story["selected_candidates"]
        }
        self.assertEqual(selected_assets, {item["id"] for item in assets})
        self.assertEqual(story["unclassified_candidates"], 8)

    def test_film_allocates_more_ceremony_than_teaser(self):
        teaser = normalize_deliverable("Casamento", "teaser", 60)
        film = normalize_deliverable("Casamento", "film", 1200)

        teaser_sections = teaser["story_budget"]["sections"]
        film_sections = film["story_budget"]["sections"]

        teaser_ratio = teaser_sections["cerimonia"] / teaser["target_seconds"]
        film_ratio = film_sections["cerimonia"] / film["target_seconds"]
        self.assertGreater(film_ratio, teaser_ratio)
        self.assertGreater(film_sections["votos_falas"], teaser_sections["votos_falas"])


if __name__ == "__main__":
    unittest.main()

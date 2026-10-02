import unittest

from core.reference_story_director import (
    arrange_candidates_by_reference,
    build_reference_story_director,
)
from core.wedding_assembly import build_wedding_assembly_plan
from renderer.multisource_renderer import _source_audio_gain


class ReferenceStoryDirectorTests(unittest.TestCase):
    def _reference_style(self):
        duration = 240000
        scenes = []
        cursor = 0
        index = 0
        while cursor < duration:
            if cursor < 175000:
                shot = 4200
            elif cursor < 220000:
                shot = 1700
            else:
                shot = 2800
            end = min(duration, cursor + shot)
            scenes.append(
                {
                    "index": index,
                    "start_ms": cursor,
                    "end_ms": end,
                    "duration_ms": end - cursor,
                }
            )
            index += 1
            cursor = end

        pacing = []
        for index in range(12):
            start_ratio = index / 12
            median_seconds = 4.2 if start_ratio < 0.70 else (1.7 if start_ratio < 0.92 else 2.8)
            pacing.append(
                {
                    "index": index,
                    "start_ratio": start_ratio,
                    "end_ratio": (index + 1) / 12,
                    "median_shot_seconds": median_seconds,
                }
            )
        return {
            "engine": "reference-rhythm-v2",
            "duration_ms": duration,
            "median_shot_seconds": 3.8,
            "scenes": scenes,
            "pacing_windows": pacing,
        }

    def _reference_music(self):
        return {
            "duration_ms": 240000,
            "transitions": [
                {"time_ms": 180000, "direction": "up", "strength": 0.35},
            ],
            "energy_sections": [
                {"start_ms": 0, "end_ms": 120000, "energy": 0.30},
                {"start_ms": 120000, "end_ms": 180000, "energy": 0.45},
                {"start_ms": 180000, "end_ms": 230000, "energy": 0.82},
                {"start_ms": 230000, "end_ms": 240000, "energy": 0.55},
            ],
        }

    def test_director_creates_cold_open_and_late_climax(self):
        director = build_reference_story_director(
            self._reference_style(),
            self._reference_music(),
            210000,
        )
        self.assertTrue(director["cold_open_enabled"])
        self.assertEqual(director["phases"][0]["key"], "cold_open")
        self.assertGreaterEqual(director["climax_start_ratio"], 0.68)
        self.assertLessEqual(director["climax_start_ratio"], 0.82)
        ceremony = next(item for item in director["phases"] if item["key"] == "ceremony")
        preparation = next(item for item in director["phases"] if item["key"] == "preparation_a")
        self.assertLess(ceremony["target_shot_ms"], preparation["target_shot_ms"])

    def test_unclassified_material_falls_back_to_source_chronology(self):
        assets = []
        candidates = []
        for index in range(30):
            asset_id = f"asset-{index:02d}"
            assets.append({"id": asset_id, "path": f"MVI_{index:04d}.MP4"})
            candidates.append(
                {
                    "asset_id": asset_id,
                    "path": f"MVI_{index:04d}.MP4",
                    "filename": f"MVI_{index:04d}.MP4",
                    "scene_id": 0,
                    "start_ms": 0,
                    "end_ms": 6000,
                    "duration_ms": 6000,
                    "score": 70 + (index % 8),
                    "quality_label": "boa",
                }
            )

        director = build_reference_story_director(
            self._reference_style(),
            self._reference_music(),
            120000,
        )
        selected = arrange_candidates_by_reference(candidates, assets, director, 60)
        self.assertTrue(selected)
        self.assertEqual(selected[0]["director_phase"], "cold_open")

        body = [
            item for item in selected
            if item.get("director_phase") in {"preparation_a", "details", "preparation_b"}
        ]
        body_indexes = [int(item["asset_id"].split("-")[1]) for item in body]
        self.assertTrue(body_indexes)
        self.assertLess(min(body_indexes), max(body_indexes))
        # O corpo não deve ser simplesmente ranking global por score.
        self.assertLess(body_indexes[0], 15)

    def test_assembly_uses_reference_director_phase_durations(self):
        assets = []
        candidates = []
        for index in range(45):
            asset_id = f"asset-{index:02d}"
            path = f"MVI_{index:04d}.MP4"
            assets.append(
                {
                    "id": asset_id,
                    "path": path,
                    "filename": path,
                    "duration_seconds": 8.0,
                    "category_hint": "nao_classificado",
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
                    "end_ms": 8000,
                    "duration_ms": 8000,
                    "score": 76.0,
                    "quality_label": "boa",
                }
            )

        director = build_reference_story_director(
            self._reference_style(),
            self._reference_music(),
            120000,
        )
        project = {
            "profile": "Casamento",
            "style": "Highlight",
            "deliverable": {
                "type": "trailer",
                "target_seconds": 120,
                "average_shot_seconds": 2.6,
                "preserve_long_form": False,
            },
            "review_settings": {"auto_zoom": False},
            "music_source_path": "music.mp3",
        }
        plan = build_wedding_assembly_plan(
            project,
            {"assets": assets},
            {"best_take_candidates": candidates},
            reference_story_director=director,
        )
        self.assertTrue(plan["reference_story_director_applied"])
        self.assertTrue(plan["cold_open_applied"])
        self.assertGreater(plan["clip_count"], 20)
        self.assertGreater(plan["estimated_duration_ms"], 100000)
        self.assertTrue(any(item["key"] == "ceremony" for item in plan["reference_story_phases"]))


class AudioPriorityRegressionTests(unittest.TestCase):
    def test_music_priority_does_not_open_ceremony_ambience(self):
        self.assertEqual(
            _source_audio_gain(
                {
                    "story_section": "cerimonia",
                    "source_audio_role": "music_priority",
                    "source_audio_gain": 0.0,
                }
            ),
            0.0,
        )


if __name__ == "__main__":
    unittest.main()

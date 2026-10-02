import unittest

from core.reference_story_director import (
    arrange_candidates_by_reference,
    build_reference_story_director,
)
from editor.reference_mapping import map_reference_timing
from editor.reference_style import build_reference_style_profile


class StoryDirectorV2Tests(unittest.TestCase):
    def _reference_style(self):
        duration = 240000
        cuts = []
        cursor = 0
        while cursor < duration:
            if cursor < 165000:
                step = 4200
            elif cursor < 220000:
                step = 1800
            else:
                step = 3200
            cursor += step
            if cursor < duration:
                cuts.append(cursor)
        return build_reference_style_profile(cuts, duration)

    def _reference_music(self):
        return {
            "duration_ms": 240000,
            "transitions": [
                {"time_ms": 174000, "direction": "up", "strength": 0.34},
                {"time_ms": 222000, "direction": "down", "strength": 0.26},
            ],
            "energy_sections": [
                {"start_ms": 0, "end_ms": 120000, "energy": 0.28},
                {"start_ms": 120000, "end_ms": 174000, "energy": 0.44},
                {"start_ms": 174000, "end_ms": 222000, "energy": 0.84},
                {"start_ms": 222000, "end_ms": 240000, "energy": 0.52},
            ],
        }

    def _material(self, count=72):
        assets = []
        candidates = []
        for index in range(count):
            asset_id = f"asset-{index:03d}"
            path = f"MVI_{index:04d}.MP4"
            assets.append({"id": asset_id, "path": path, "filename": path})
            candidates.append(
                {
                    "asset_id": asset_id,
                    "path": path,
                    "filename": path,
                    "scene_id": 0,
                    "start_ms": 0,
                    "end_ms": 7000,
                    "duration_ms": 7000,
                    "score": 72.0 + (index % 9),
                    "quality_label": "boa",
                }
            )
        return assets, candidates

    def test_v2_builds_bounded_preview_and_story_slots(self):
        director = build_reference_story_director(
            self._reference_style(),
            self._reference_music(),
            210000,
        )
        self.assertEqual(director["engine"], "reference-story-director-v2")
        self.assertEqual(director["exact_cut_owner"], "new_music_reference_mapping")
        cold = director["phases"][0]
        self.assertEqual(cold["key"], "cold_open")
        self.assertGreaterEqual(cold["desired_shots"], 4)
        self.assertLessEqual(cold["desired_shots"], 6)
        self.assertTrue(any(item["key"] == "ceremony" for item in director["phases"]))
        self.assertTrue(any(item["key"] == "finale" for item in director["phases"]))

    def test_arrangement_keeps_phases_in_order_without_chronology_tail(self):
        assets, candidates = self._material()
        director = build_reference_story_director(
            self._reference_style(),
            self._reference_music(),
            180000,
        )
        selected = arrange_candidates_by_reference(candidates, assets, director, 100)
        self.assertTrue(selected)
        phase_order = [item["key"] for item in director["phases"]]
        seen = [item["director_phase"] for item in selected]
        self.assertNotIn("chronology_fill", seen)
        positions = [phase_order.index(value) for value in seen]
        self.assertEqual(positions, sorted(positions))
        self.assertTrue(all(item["director_target_duration_ms"] is None for item in selected))

    def test_unclassified_body_progresses_through_source_material(self):
        assets, candidates = self._material(60)
        director = build_reference_story_director(
            self._reference_style(),
            self._reference_music(),
            150000,
        )
        selected = arrange_candidates_by_reference(candidates, assets, director, 90)
        prep = [item for item in selected if item["director_phase"] == "preparation_a"]
        ceremony = [item for item in selected if item["director_phase"] == "ceremony"]
        self.assertTrue(prep)
        self.assertTrue(ceremony)
        prep_indexes = [int(item["asset_id"].split("-")[1]) for item in prep]
        ceremony_indexes = [int(item["asset_id"].split("-")[1]) for item in ceremony]
        self.assertLess(sum(prep_indexes) / len(prep_indexes), sum(ceremony_indexes) / len(ceremony_indexes))


class MusicPhraseDirectorTests(unittest.TestCase):
    def test_phrase_boundaries_are_sparse_and_strong(self):
        reference = build_reference_style_profile(
            [4000, 8000, 12000, 16000, 20000, 24000, 28000],
            32000,
        )
        music = {
            "duration_ms": 32000,
            "edit_points_ms": [3900, 8100, 11900, 16100, 19900, 23900, 28100],
            "transitions": [
                {"time_ms": 8000, "direction": "up", "strength": 0.31},
                {"time_ms": 16000, "direction": "up", "strength": 0.42},
                {"time_ms": 24000, "direction": "down", "strength": 0.35},
            ],
            "energy_peaks": [
                {"time_ms": 4000, "strength": 0.91},
                {"time_ms": 12000, "strength": 0.93},
                {"time_ms": 20000, "strength": 0.95},
                {"time_ms": 28000, "strength": 0.94},
            ],
            "energy_sections": [
                {"start_ms": 0, "end_ms": 8000, "energy": 0.3},
                {"start_ms": 8000, "end_ms": 16000, "energy": 0.45},
                {"start_ms": 16000, "end_ms": 24000, "energy": 0.82},
                {"start_ms": 24000, "end_ms": 32000, "energy": 0.55},
            ],
        }
        mapped = map_reference_timing(
            reference,
            32000,
            music_analysis=music,
            snap_window_ms=300,
        )
        points = mapped["music_phrase_points_ms"]
        self.assertTrue(points)
        self.assertGreater(mapped["music_phrase_count"], 1)
        self.assertTrue(all(b - a >= 6000 for a, b in zip(points, points[1:])))
        self.assertGreaterEqual(mapped["minimum_shot_ms"], 850)
        self.assertLess(mapped["music_phrase_count"], mapped["shot_count"])


if __name__ == "__main__":
    unittest.main()

import unittest

from editor.reference_mapping import map_reference_timing
from editor.reference_style import build_reference_style_profile


class ReferenceMappingTests(unittest.TestCase):
    def test_reference_cuts_scale_to_new_duration(self):
        reference = build_reference_style_profile(
            [1000, 2000, 3000, 4000],
            5000,
        )
        mapped = map_reference_timing(
            reference,
            10000,
            minimum_shot_ms=300,
        )

        self.assertEqual(mapped["cut_points_ms"], [2000, 4000, 6000, 8000])
        self.assertEqual(mapped["shot_count"], 5)
        self.assertFalse(mapped["music_snap_enabled"])

    def test_reference_cuts_snap_to_new_music_points(self):
        reference = build_reference_style_profile(
            [1000, 2000, 3000, 4000],
            5000,
        )
        music = {
            "edit_points_ms": [1900, 4100, 5900, 8050],
        }
        mapped = map_reference_timing(
            reference,
            10000,
            music_analysis=music,
            snap_window_ms=250,
            minimum_shot_ms=300,
        )

        self.assertEqual(mapped["cut_points_ms"], [1900, 4100, 5900, 8050])
        self.assertTrue(mapped["music_snap_enabled"])
        self.assertEqual(mapped["music_edit_points_available"], 4)

    def test_mapping_preserves_reference_sections_proportionally(self):
        reference = build_reference_style_profile(
            [1500, 4500, 7000, 9000],
            10000,
        )
        mapped = map_reference_timing(
            reference,
            20000,
            minimum_shot_ms=300,
        )

        self.assertEqual(mapped["sections"]["intro"]["end_ms"], 3000)
        self.assertEqual(mapped["sections"]["climax"]["start_ms"], 11000)
        self.assertEqual(mapped["sections"]["finale"]["end_ms"], 20000)


if __name__ == "__main__":
    unittest.main()

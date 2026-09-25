import unittest

from editor.edit_plan import build_edit_plan
from editor.review import (
    adjust_removed_segment,
    remove_range,
    remove_segment,
    restore_cut,
    split_at,
)
from profiles import (
    get_edit_rules,
    profile_names,
    styles_for_profile,
)
from renderer.export_profiles import get_export_profile


class ProfileCatalogTests(unittest.TestCase):
    def test_all_expected_profiles_are_registered(self):
        names = profile_names()

        for expected in (
            "YouTube",
            "Shorts / Reels / TikTok",
            "Podcast",
            "Gaming",
            "Curso",
            "VSL",
            "Institucional",
            "Casamento",
        ):
            self.assertIn(expected, names)
            self.assertTrue(styles_for_profile(expected))

    def test_each_style_has_rules(self):
        for profile in profile_names():
            for style in styles_for_profile(profile):
                rules = get_edit_rules(profile, style)
                self.assertEqual(rules.profile, profile)
                self.assertEqual(rules.style, style)

    def test_wedding_does_not_remove_silence_automatically(self):
        plan = build_edit_plan(
            10000,
            "Casamento",
            "Highlight",
            {
                "silences": [
                    {
                        "start_ms": 1000,
                        "end_ms": 6000,
                        "duration_ms": 5000,
                    }
                ]
            },
        )

        self.assertEqual(plan["stats"]["cuts"], 0)
        self.assertEqual(
            plan["stats"]["estimated_duration_ms"],
            10000,
        )

    def test_export_profiles_include_low_resolution(self):
        self.assertEqual(
            get_export_profile("480p").height,
            480,
        )
        self.assertEqual(
            get_export_profile("360p").height,
            360,
        )


class TimelineManualEditingTests(unittest.TestCase):
    def setUp(self):
        self.plan = build_edit_plan(
            10000,
            "YouTube",
            "Dinâmico",
            {"silences": []},
        )

    def test_split_then_remove_selected_segment(self):
        split = split_at(self.plan, 4000)
        self.assertEqual(len(split["segments"]), 2)

        removed = remove_segment(split, 0)
        self.assertEqual(
            removed["segments"][0]["action"],
            "remove",
        )
        self.assertEqual(
            removed["stats"]["removed_duration_ms"],
            4000,
        )

    def test_remove_manual_range(self):
        updated = remove_range(
            self.plan,
            2500,
            4200,
        )

        self.assertEqual(
            updated["stats"]["removed_duration_ms"],
            1700,
        )
        self.assertEqual(updated["stats"]["cuts"], 1)

    def test_restore_manual_cut(self):
        removed = remove_range(
            self.plan,
            2000,
            3000,
        )
        index = next(
            i
            for i, segment in enumerate(removed["segments"])
            if segment["action"] == "remove"
        )

        restored = restore_cut(removed, index)

        self.assertEqual(
            restored["segments"][index]["action"],
            "keep",
        )
        self.assertEqual(
            restored["stats"]["removed_duration_ms"],
            0,
        )

    def test_adjust_removed_segment_boundaries(self):
        removed = remove_range(
            self.plan,
            2000,
            4000,
        )
        index = next(
            i
            for i, segment in enumerate(removed["segments"])
            if segment["action"] == "remove"
        )

        adjusted = adjust_removed_segment(
            removed,
            index,
            new_start_ms=1800,
            new_end_ms=4300,
        )

        segment = adjusted["segments"][index]
        self.assertEqual(segment["start_ms"], 1800)
        self.assertEqual(segment["end_ms"], 4300)
        self.assertEqual(
            adjusted["stats"]["removed_duration_ms"],
            2500,
        )


if __name__ == "__main__":
    unittest.main()

import unittest

from core.best_shot_selector import (
    candidate_selection_score,
    is_usable_wedding_candidate,
)
from renderer.multisource_renderer import (
    _dialogue_focus_indexes,
    _input_window,
    _select_slow_motion_rates,
)


def semantics(tags=None, *, whip=0.0, shake=0.0, blur=0.0, hero=0.0, highlight=0.0):
    return {
        "tags": [
            {"name": name, "score": score}
            for name, score in (tags or {}).items()
        ],
        "quality": {
            "whip_score": whip,
            "shake_score": shake,
            "motion_blur_score": blur,
        },
        "roles": {
            "hero_score": hero,
            "highlight_score": highlight,
        },
    }


class MotionRiskSelectionTests(unittest.TestCase):
    def test_high_internal_whip_is_rejected(self):
        candidate = {
            "duration_ms": 3200,
            "score": 88,
            "quality_label": "boa",
            "visual_semantics": semantics(whip=0.76),
        }
        self.assertFalse(is_usable_wedding_candidate(candidate))

    def test_small_motion_risk_only_penalizes_score(self):
        stable = {
            "duration_ms": 3200,
            "score": 80,
            "quality_label": "boa",
            "visual_semantics": semantics(),
        }
        moving = {
            **stable,
            "visual_semantics": semantics(whip=0.20, shake=0.12, blur=0.10),
        }
        self.assertTrue(is_usable_wedding_candidate(moving))
        self.assertLess(candidate_selection_score(moving), candidate_selection_score(stable))


class SlowMotionDirectorTests(unittest.TestCase):
    def test_hero_60fps_gets_slow_motion_but_30fps_does_not(self):
        clips = [
            {
                "duration_ms": 3600,
                "story_section": "casal",
                "source_audio_role": "music_priority",
                "visual_semantics": semantics(
                    {"couple_portrait": 0.78, "hero_shot_candidate": 0.72},
                    hero=0.80,
                    highlight=0.72,
                ),
            },
            {
                "duration_ms": 3600,
                "story_section": "casal",
                "source_audio_role": "music_priority",
                "visual_semantics": semantics(
                    {"kiss": 0.84},
                    hero=0.76,
                    highlight=0.81,
                ),
            },
        ]
        rates = _select_slow_motion_rates(clips, [60.0, 30.0])
        self.assertLess(rates[0], 1.0)
        self.assertEqual(rates[1], 1.0)

    def test_dialogue_never_becomes_slow_motion(self):
        clip = {
            "duration_ms": 4200,
            "story_section": "votos_falas",
            "source_audio_role": "dialogue",
            "visual_semantics": semantics(
                {"vows": 0.80, "couple_closeup": 0.72},
                hero=0.70,
            ),
        }
        self.assertEqual(_select_slow_motion_rates([clip], [60.0]), [1.0])

    def test_slow_input_window_is_centered_and_shorter(self):
        start, duration = _input_window(
            {"start_ms": 1000, "duration_ms": 4000},
            0.60,
        )
        self.assertEqual(duration, 2400)
        self.assertEqual(start, 1800)


class DialogueFocusTests(unittest.TestCase):
    def test_visual_vows_can_open_one_real_voice_moment(self):
        clips = [
            {
                "duration_ms": 3500,
                "story_section": "cerimonia",
                "source_audio_role": "music_priority",
                "visual_semantics": semantics({"vows": 0.62}),
            },
            {
                "duration_ms": 3500,
                "story_section": "cerimonia",
                "source_audio_role": "music_priority",
                "visual_semantics": semantics({"ceremony_wide": 0.70, "vows": 0.05}),
            },
        ]
        focus = _dialogue_focus_indexes(clips, [True, True])
        self.assertEqual(focus, {0})

    def test_no_audio_never_becomes_dialogue_focus(self):
        clip = {
            "duration_ms": 3500,
            "story_section": "votos_falas",
            "source_audio_role": "dialogue",
            "visual_semantics": semantics({"vows": 0.85}),
        }
        self.assertEqual(_dialogue_focus_indexes([clip], [False]), set())


if __name__ == "__main__":
    unittest.main()

import unittest

from core.best_shot_selector import (
    candidate_selection_score,
    is_usable_wedding_candidate,
    rank_wedding_candidates,
)
from renderer.multisource_renderer import _source_audio_gain


class WeddingQualityGateTests(unittest.TestCase):
    def test_weak_take_remains_only_as_low_priority_fallback(self):
        weak = {
            "duration_ms": 2500,
            "score": 44.0,
            "quality_label": "fraca",
            "quality_sampled": True,
        }
        good = {
            "duration_ms": 2500,
            "score": 78.0,
            "quality_label": "boa",
            "quality_sampled": True,
        }

        self.assertTrue(is_usable_wedding_candidate(weak))
        ranked = rank_wedding_candidates([weak, good])
        self.assertEqual(len(ranked), 2)
        self.assertEqual(ranked[0]["quality_label"], "boa")
        self.assertLess(
            candidate_selection_score(weak),
            candidate_selection_score(good),
        )

    def test_catastrophically_weak_sampled_take_is_rejected(self):
        candidate = {
            "duration_ms": 2500,
            "score": 20.0,
            "quality_label": "fraca",
            "quality_sampled": True,
        }
        self.assertFalse(is_usable_wedding_candidate(candidate))
        self.assertEqual(rank_wedding_candidates([candidate]), [])

    def test_unsampled_estimate_is_not_rejected_without_evidence(self):
        candidate = {
            "duration_ms": 2500,
            "score": 60.0,
            "quality_label": "fraca",
            "quality_sampled": False,
        }
        self.assertTrue(is_usable_wedding_candidate(candidate))
        self.assertEqual(len(rank_wedding_candidates([candidate])), 1)

    def test_very_short_take_is_rejected(self):
        self.assertFalse(
            is_usable_wedding_candidate(
                {"duration_ms": 300, "score": 90.0, "quality_sampled": True}
            )
        )


class WeddingAudioDirectorTests(unittest.TestCase):
    def test_dialogue_stays_in_front(self):
        self.assertEqual(
            _source_audio_gain(
                {
                    "story_section": "votos_falas",
                    "source_audio_role": "dialogue",
                    "source_audio_gain": 1.0,
                }
            ),
            1.0,
        )

    def test_ceremony_ambience_opens_under_music(self):
        self.assertAlmostEqual(
            _source_audio_gain(
                {
                    "story_section": "cerimonia",
                    "source_audio_role": "music_only",
                    "source_audio_gain": 0.0,
                }
            ),
            0.42,
        )

    def test_party_broll_remains_muted_to_avoid_two_songs(self):
        self.assertEqual(
            _source_audio_gain(
                {
                    "story_section": "festa",
                    "source_audio_role": "music_only",
                    "source_audio_gain": 0.0,
                }
            ),
            0.0,
        )


if __name__ == "__main__":
    unittest.main()

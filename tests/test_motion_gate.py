import unittest

from core.batch_visual_analysis import BatchVisualAnalysisPipeline
from core.wedding_assembly import _window
from media.motion_analyzer import profile_scene_motion


class MotionGateTests(unittest.TestCase):
    def test_stable_scene_is_preserved(self):
        samples = [
            {"time_ms": value, "motion": 2.0 + (value % 3) * 0.2}
            for value in range(0, 3001, 250)
        ]
        profile = profile_scene_motion(samples, 0, 3000)
        self.assertEqual(profile["classification"], "stable")
        self.assertEqual(profile["trim_start_ms"], 0)
        self.assertEqual(profile["trim_end_ms"], 0)

    def test_entry_whip_trims_only_beginning(self):
        samples = [
            {"time_ms": 0, "motion": 18.0},
            {"time_ms": 200, "motion": 16.0},
            {"time_ms": 400, "motion": 12.0},
            {"time_ms": 650, "motion": 3.0},
            {"time_ms": 1000, "motion": 2.5},
            {"time_ms": 1500, "motion": 2.4},
            {"time_ms": 2000, "motion": 2.6},
            {"time_ms": 2500, "motion": 2.5},
            {"time_ms": 3000, "motion": 2.4},
        ]
        profile = profile_scene_motion(samples, 0, 3000)
        self.assertEqual(profile["classification"], "entry_whip")
        self.assertGreater(profile["trim_start_ms"], 0)
        self.assertEqual(profile["trim_end_ms"], 0)
        self.assertGreaterEqual(profile["safe_end_ms"] - profile["safe_start_ms"], 650)

    def test_exit_whip_trims_only_end(self):
        samples = [
            {"time_ms": 0, "motion": 2.4},
            {"time_ms": 500, "motion": 2.5},
            {"time_ms": 1000, "motion": 2.6},
            {"time_ms": 1500, "motion": 2.4},
            {"time_ms": 2000, "motion": 2.5},
            {"time_ms": 2400, "motion": 11.0},
            {"time_ms": 2600, "motion": 15.0},
            {"time_ms": 2800, "motion": 18.0},
            {"time_ms": 3000, "motion": 16.0},
        ]
        profile = profile_scene_motion(samples, 0, 3000)
        self.assertEqual(profile["classification"], "exit_whip")
        self.assertEqual(profile["trim_start_ms"], 0)
        self.assertGreater(profile["trim_end_ms"], 0)

    def test_continuous_camera_motion_is_not_trimmed(self):
        samples = [
            {"time_ms": value, "motion": 8.0 + ((value // 250) % 3) * 0.8}
            for value in range(0, 3001, 250)
        ]
        profile = profile_scene_motion(samples, 0, 3000)
        self.assertEqual(profile["classification"], "continuous_motion")
        self.assertEqual(profile["trim_start_ms"], 0)
        self.assertEqual(profile["trim_end_ms"], 0)

    def test_short_middle_spike_is_marked_as_internal_whip(self):
        samples = [
            {"time_ms": 0, "motion": 2.4},
            {"time_ms": 400, "motion": 2.5},
            {"time_ms": 800, "motion": 2.6},
            {"time_ms": 1100, "motion": 2.4},
            {"time_ms": 1400, "motion": 17.0},
            {"time_ms": 1700, "motion": 2.5},
            {"time_ms": 2000, "motion": 2.6},
            {"time_ms": 2400, "motion": 2.4},
            {"time_ms": 2800, "motion": 2.5},
            {"time_ms": 3200, "motion": 2.4},
        ]
        profile = profile_scene_motion(samples, 0, 3200)
        self.assertEqual(profile["classification"], "internal_whip")
        self.assertGreater(profile["confidence"], 0.0)
        self.assertEqual(profile["trim_start_ms"], 0)
        self.assertEqual(profile["trim_end_ms"], 0)
        self.assertEqual(profile["internal_spike_samples"], 1)

    def test_batch_candidate_receives_motion_safe_bounds(self):
        target = []
        asset = {
            "id": "asset-a",
            "path": "a.mp4",
            "filename": "a.mp4",
            "category_hint": "casal",
            "audio_present": True,
        }
        visual = {
            "scenes": [
                {
                    "id": 3,
                    "start_ms": 1000,
                    "end_ms": 5000,
                    "duration_ms": 4000,
                    "quality": {
                        "score": 84.0,
                        "label": "excelente",
                        "sampled": True,
                    },
                }
            ]
        }
        motion = {
            "scenes": [
                {
                    "scene_id": 3,
                    "classification": "exit_whip",
                    "confidence": 0.8,
                    "safe_start_ms": 1000,
                    "safe_end_ms": 4400,
                    "trim_start_ms": 0,
                    "trim_end_ms": 600,
                    "median_motion": 2.4,
                    "peak_motion": 18.0,
                }
            ]
        }

        BatchVisualAnalysisPipeline._collect_candidates(
            target,
            asset,
            visual,
            motion_result=motion,
        )
        self.assertEqual(len(target), 1)
        self.assertEqual(target[0]["motion_classification"], "exit_whip")
        self.assertEqual(target[0]["motion_safe_end_ms"], 4400)
        self.assertEqual(target[0]["motion_trim_end_ms"], 600)

    def test_window_never_reintroduces_trimmed_whip(self):
        candidate = {
            "asset_id": "a",
            "path": "a.mp4",
            "filename": "a.mp4",
            "start_ms": 1000,
            "end_ms": 7000,
            "duration_ms": 6000,
            "score": 80.0,
            "motion_classification": "edge_whip_both",
            "motion_confidence": 0.9,
            "motion_safe_start_ms": 1600,
            "motion_safe_end_ms": 6300,
            "motion_trim_start_ms": 600,
            "motion_trim_end_ms": 700,
        }
        clip = _window(candidate, 3000)
        self.assertIsNotNone(clip)
        self.assertTrue(clip["motion_gate_applied"])
        self.assertGreaterEqual(clip["start_ms"], 1600)
        self.assertLessEqual(clip["end_ms"], 6300)
        self.assertEqual(clip["source_start_ms"], 1600)
        self.assertEqual(clip["source_end_ms"], 6300)
        self.assertEqual(clip["motion_trim_total_ms"], 1300)


if __name__ == "__main__":
    unittest.main()

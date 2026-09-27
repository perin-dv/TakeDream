import math
import tempfile
import unittest
import wave
from pathlib import Path
from struct import pack

from core.music_pipeline import MusicAnalysisPipeline
from core.project_manager import ProjectManager
from editor.reference_style import build_reference_style_profile
from media.music_analyzer import MusicAnalyzer


class _ToolsWithoutFFmpeg:
    ffmpeg_path = None


class ReferenceStyleTests(unittest.TestCase):
    def test_reference_profile_measures_cut_rhythm(self):
        profile = build_reference_style_profile(
            [1000, 2000, 3000, 4000, 5000],
            6000,
        )
        self.assertEqual(profile["scene_count"], 6)
        self.assertEqual(profile["cut_count"], 5)
        self.assertEqual(profile["rhythm"], "rapido")
        self.assertAlmostEqual(profile["average_shot_seconds"], 1.0, places=2)
        self.assertIn("climax", profile["sections"])
        self.assertEqual(profile["sections"]["finale"]["end_ms"], 6000)

    def test_reference_profile_distinguishes_slow_editing(self):
        profile = build_reference_style_profile(
            [10000, 20000],
            30000,
        )
        self.assertEqual(profile["rhythm"], "lento")
        self.assertAlmostEqual(profile["median_shot_seconds"], 10.0, places=2)


class MusicAnalyzerTests(unittest.TestCase):
    def _pulse_wav(self, path, duration_seconds=5.0, bpm=120):
        sample_rate = 8000
        frames = int(duration_seconds * sample_rate)
        beat_interval = 60.0 / bpm
        samples = []

        for index in range(frames):
            time_s = index / sample_rate
            phase = time_s % beat_interval
            if phase < 0.055:
                value = int(26000 * math.sin(2 * math.pi * 220 * time_s))
            else:
                value = int(450 * math.sin(2 * math.pi * 110 * time_s))
            samples.append(value)

        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(sample_rate)
            handle.writeframes(b"".join(pack("<h", value) for value in samples))

    def test_music_analyzer_finds_energy_edit_points_and_tempo(self):
        with tempfile.TemporaryDirectory() as temporary:
            wav_path = Path(temporary) / "track.wav"
            self._pulse_wav(wav_path)
            result = MusicAnalyzer.analyze_wav(wav_path)

        self.assertGreater(result["energy_peak_count"], 4)
        self.assertTrue(result["edit_points_ms"])
        self.assertEqual(len(result["energy_sections"]), 8)
        self.assertIsNotNone(result["tempo_bpm_estimate"])
        self.assertGreaterEqual(result["tempo_bpm_estimate"], 100)
        self.assertLessEqual(result["tempo_bpm_estimate"], 140)

    def test_music_pipeline_reuses_cached_analysis(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.mp4"
            source.touch()
            music = root / "track.wav"
            self._pulse_wav(music, duration_seconds=3.0)

            manager = ProjectManager(root / "projects")
            project = manager.create_project(
                "Wedding Music",
                source,
                "Casamento",
                "Highlight",
            )
            pipeline = MusicAnalysisPipeline(
                manager=manager,
                tools=_ToolsWithoutFFmpeg(),
            )
            first = pipeline.run(project, music)
            second = pipeline.run(project, music)

        self.assertFalse(first["reused"])
        self.assertTrue(second["reused"])
        self.assertEqual(
            first["music_analysis"]["edit_points_ms"],
            second["music_analysis"]["edit_points_ms"],
        )


if __name__ == "__main__":
    unittest.main()

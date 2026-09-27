import tempfile
import unittest
from pathlib import Path

from core.render_settings import normalize_render_settings
from editor.edit_plan import build_edit_plan
from renderer.audio import (
    audio_filter_chain,
    normalize_audio_settings,
)
from renderer.captions import write_ass_captions
from renderer.ffmpeg_renderer import build_filter_graph
from renderer.reframe import (
    normalize_focus_region,
    smart_crop_box,
)


class SmartReframeTests(unittest.TestCase):
    def test_focus_region_moves_vertical_crop(self):
        centered = smart_crop_box(
            1920,
            1080,
            "9:16",
            {"x": 0.5, "y": 0.5},
        )
        right = smart_crop_box(
            1920,
            1080,
            "9:16",
            {"x": 0.8, "y": 0.5},
        )

        self.assertEqual(centered["width"], 608)
        self.assertEqual(centered["height"], 1080)
        self.assertGreater(right["x"], centered["x"])
        self.assertEqual(right["y"], 0)

    def test_focus_region_is_clamped(self):
        focus = normalize_focus_region(
            {"x": 3, "y": -2, "source": "manual"}
        )

        self.assertEqual(focus.x, 1.0)
        self.assertEqual(focus.y, 0.0)
        self.assertEqual(focus.source, "manual")


class AudioV1Tests(unittest.TestCase):
    def test_audio_filter_is_opt_in_for_low_level_renderer(self):
        self.assertIsNone(
            audio_filter_chain(None)
        )

    def test_audio_filter_contains_loudness_and_limiter(self):
        chain = audio_filter_chain(
            {
                "enabled": True,
                "target_lufs": -16,
                "lra": 11,
                "true_peak": -1.5,
                "limiter": 0.95,
            }
        )

        self.assertIn("loudnorm=", chain)
        self.assertIn("I=-16.0", chain)
        self.assertIn("TP=-1.5", chain)
        self.assertIn("alimiter=", chain)

    def test_audio_values_are_safely_clamped(self):
        settings = normalize_audio_settings(
            {
                "target_lufs": -100,
                "true_peak": 2,
                "limiter": 5,
            }
        )

        self.assertEqual(settings["target_lufs"], -24.0)
        self.assertEqual(settings["true_peak"], -0.1)
        self.assertEqual(settings["limiter"], 1.0)


class CaptionV2Tests(unittest.TestCase):
    def _plan(self):
        return build_edit_plan(
            5000,
            "YouTube",
            "Dinâmico",
            {"silences": []},
        )

    def _transcript(self):
        return {
            "segments": [
                {
                    "id": 0,
                    "start_ms": 0,
                    "end_ms": 1800,
                    "text": "Olá mundo incrível",
                    "words": [
                        {
                            "start_ms": 100,
                            "end_ms": 450,
                            "word": "Olá",
                            "probability": 1.0,
                        },
                        {
                            "start_ms": 500,
                            "end_ms": 900,
                            "word": "mundo",
                            "probability": 1.0,
                        },
                        {
                            "start_ms": 950,
                            "end_ms": 1450,
                            "word": "incrível",
                            "probability": 1.0,
                        },
                    ],
                }
            ]
        }

    def test_dynamic_caption_uses_word_timing(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "dynamic.ass"
            write_ass_captions(
                self._transcript(),
                self._plan(),
                path,
                style="Dinâmica",
                play_res_x=1080,
                play_res_y=1920,
            )
            text = path.read_text(
                encoding="utf-8-sig"
            )

            self.assertIn(r"\kf", text)
            self.assertIn("Olá", text)
            self.assertIn("PlayResX: 1080", text)
            self.assertIn("PlayResY: 1920", text)

    def test_clean_caption_remains_readable_without_karaoke(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "clean.ass"
            write_ass_captions(
                self._transcript(),
                self._plan(),
                path,
                style="Clean",
                play_res_x=1920,
                play_res_y=1080,
            )
            text = path.read_text(
                encoding="utf-8-sig"
            )

            self.assertNotIn(r"\kf", text)
            self.assertIn("Olá mundo incrível", text)


class RendererV4GraphTests(unittest.TestCase):
    def test_graph_uses_focus_crop_and_audio_treatment(self):
        plan = build_edit_plan(
            6000,
            "YouTube",
            "Dinâmico",
            {"silences": []},
        )

        graph = build_filter_graph(
            plan,
            source_width=1920,
            source_height=1080,
            target_aspect_ratio="9:16",
            output_size=(720, 1280),
            smart_reframe=True,
            focus_region={
                "x": 0.8,
                "y": 0.5,
                "source": "manual",
            },
            audio_settings={
                "enabled": True,
                "target_lufs": -16,
                "lra": 11,
                "true_peak": -1.5,
                "limiter": 0.95,
            },
        )

        self.assertIn(
            "crop=608:1080:1232:0",
            graph,
        )
        self.assertIn("scale=720:1280", graph)
        self.assertIn("loudnorm=", graph)
        self.assertIn("alimiter=", graph)

    def test_render_settings_enable_v4_defaults(self):
        settings = normalize_render_settings(
            None,
            {
                "aspect_ratio": "9:16",
                "style": "Dinâmico",
                "focus_region": {
                    "x": 0.7,
                    "y": 0.4,
                    "source": "manual",
                },
            },
        )

        self.assertTrue(settings["smart_reframe"])
        self.assertTrue(settings["audio_enhance"])
        self.assertEqual(
            settings["focus_region"]["x"],
            0.7,
        )
        self.assertTrue(
            settings["audio_settings"]["enabled"]
        )


if __name__ == "__main__":
    unittest.main()

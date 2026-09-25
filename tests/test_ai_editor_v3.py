import tempfile
import unittest
from pathlib import Path

from core.project_manager import ProjectManager
from core.render_settings import (
    normalize_render_settings,
)
from editor.content_analysis import analyze_content
from editor.edit_plan import build_edit_plan
from renderer.captions import write_ass_captions
from renderer.ffmpeg_renderer import build_filter_graph
from renderer.formats import (
    crop_dimensions,
    target_dimensions,
)


class FormatTests(unittest.TestCase):
    def test_common_output_dimensions(self):
        self.assertEqual(
            target_dimensions(
                1920,
                1080,
                "16:9",
                short_side=720,
            ),
            (1280, 720),
        )
        self.assertEqual(
            target_dimensions(
                1920,
                1080,
                "9:16",
                short_side=720,
            ),
            (720, 1280),
        )
        self.assertEqual(
            target_dimensions(
                1920,
                1080,
                "1:1",
                short_side=720,
            ),
            (720, 720),
        )
        self.assertEqual(
            target_dimensions(
                1920,
                1080,
                "4:5",
                short_side=720,
            ),
            (720, 900),
        )

    def test_vertical_crop_does_not_stretch(self):
        width, height = crop_dimensions(
            1920,
            1080,
            "9:16",
        )

        self.assertEqual(height, 1080)
        self.assertEqual(width, 608)

    def test_project_can_override_profile_format(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "video.mp4"
            source.write_bytes(b"video")

            manager = ProjectManager(
                root / "projects"
            )
            project = manager.create_project(
                "Quadrado",
                source,
                "YouTube",
                "Dinâmico",
                aspect_ratio="1:1",
            )

            _, data = manager.load_project(
                project
            )

            self.assertEqual(
                data["aspect_ratio"],
                "1:1",
            )
            self.assertEqual(
                data["orientation"],
                "square",
            )

    def test_render_settings_are_validated(self):
        project = {
            "aspect_ratio": "16:9",
        }
        settings = normalize_render_settings(
            {
                "aspect_ratio": "9:16",
                "captions_enabled": 1,
                "caption_style": "Impacto",
                "auto_zoom": True,
            },
            project,
        )

        self.assertEqual(
            settings["aspect_ratio"],
            "9:16",
        )
        self.assertTrue(
            settings["captions_enabled"]
        )
        self.assertEqual(
            settings["caption_style"],
            "Impacto",
        )


class ContentAnalysisTests(unittest.TestCase):
    def _transcript(self):
        return {
            "schema_version": "0.1",
            "segments": [
                {
                    "id": 0,
                    "start_ms": 0,
                    "end_ms": 3500,
                    "text": (
                        "Ah hoje vamos mostrar um projeto "
                        "automotivo muito interessante"
                    ),
                    "words": [
                        {
                            "start_ms": 0,
                            "end_ms": 250,
                            "word": "Ah",
                            "probability": 0.99,
                        },
                        {
                            "start_ms": 300,
                            "end_ms": 650,
                            "word": "hoje",
                            "probability": 0.99,
                        },
                    ],
                },
                {
                    "id": 1,
                    "start_ms": 4000,
                    "end_ms": 7000,
                    "text": (
                        "Hoje vamos mostrar um projeto "
                        "automotivo muito interessante"
                    ),
                    "words": [],
                },
                {
                    "id": 2,
                    "start_ms": 20000,
                    "end_ms": 23500,
                    "text": (
                        "Agora veja o motor completo "
                        "e o sistema de transmissão"
                    ),
                    "words": [],
                },
            ],
        }

    def test_analysis_finds_editor_suggestions(self):
        analysis = analyze_content(
            self._transcript(),
            profile="YouTube",
            style="Dinâmico",
        )

        self.assertGreaterEqual(
            analysis["summary"]["fillers"],
            1,
        )
        self.assertGreaterEqual(
            analysis["summary"][
                "possible_repetitions"
            ],
            1,
        )
        self.assertGreaterEqual(
            analysis["summary"][
                "broll_suggestions"
            ],
            1,
        )
        self.assertGreaterEqual(
            analysis["summary"]["zoom_events"],
            1,
        )


class CaptionAndFilterTests(unittest.TestCase):
    def test_removed_word_is_not_burned_into_caption(self):
        plan = build_edit_plan(
            5000,
            "YouTube",
            "Dinâmico",
            {
                "silences": [
                    {
                        "start_ms": 1000,
                        "end_ms": 2200,
                        "duration_ms": 1200,
                    }
                ]
            },
        )

        transcript = {
            "segments": [
                {
                    "id": 0,
                    "start_ms": 0,
                    "end_ms": 900,
                    "text": "FICA",
                    "words": [
                        {
                            "start_ms": 100,
                            "end_ms": 500,
                            "word": "FICA",
                            "probability": 1.0,
                        }
                    ],
                },
                {
                    "id": 1,
                    "start_ms": 1200,
                    "end_ms": 1500,
                    "text": "REMOVIDA",
                    "words": [
                        {
                            "start_ms": 1200,
                            "end_ms": 1500,
                            "word": "REMOVIDA",
                            "probability": 1.0,
                        }
                    ],
                },
                {
                    "id": 2,
                    "start_ms": 2500,
                    "end_ms": 3000,
                    "text": "VOLTA",
                    "words": [
                        {
                            "start_ms": 2500,
                            "end_ms": 3000,
                            "word": "VOLTA",
                            "probability": 1.0,
                        }
                    ],
                },
            ]
        }

        with tempfile.TemporaryDirectory() as temporary:
            destination = (
                Path(temporary)
                / "captions.ass"
            )
            write_ass_captions(
                transcript,
                plan,
                destination,
                style="Impacto",
                play_res_x=1080,
                play_res_y=1920,
            )

            content = destination.read_text(
                encoding="utf-8-sig"
            )

            self.assertIn(
                "FICA",
                content,
            )
            self.assertIn(
                "VOLTA",
                content,
            )
            self.assertNotIn(
                "REMOVIDA",
                content,
            )

    def test_filter_graph_contains_crop_zoom_and_captions(self):
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
            zoom_events=[
                {
                    "start_ms": 1000,
                    "end_ms": 2000,
                    "scale": 1.07,
                }
            ],
            caption_file=Path(
                "C:/Temp/captions.ass"
            ),
        )

        self.assertIn(
            "crop=608:1080",
            graph,
        )
        self.assertIn(
            "scale=720:1280",
            graph,
        )
        self.assertIn(
            "scale=2054:1156",
            graph,
        )
        self.assertIn(
            "ass=filename=",
            graph,
        )


if __name__ == "__main__":
    unittest.main()

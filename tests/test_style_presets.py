import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.edit_pipeline import AutoEditPipeline
from core.project_manager import ProjectManager
from core.render_settings import default_render_settings
from editor.content_analysis import analyze_content
from core.storage import write_json
from editor.edit_plan import build_edit_plan
from tests.helpers import (
    make_wav,
    silences,
    transcript,
)

from profiles import (
    get_edit_rules,
    get_style_preset,
    profile_names,
    styles_for_profile,
)


class StylePresetCatalogTests(unittest.TestCase):
    def test_every_profile_style_has_rules_and_preset(self):
        for profile in profile_names():
            for style in styles_for_profile(profile):
                rules = get_edit_rules(profile, style)
                preset = get_style_preset(style)

                self.assertEqual(rules.profile, profile)
                self.assertEqual(rules.style, style)
                self.assertTrue(preset.description)
                self.assertTrue(preset.icon)
                self.assertTrue(
                    preset.caption_style
                    in ("Clean", "Dinâmica", "Impacto")
                )

    def test_youtube_has_extended_styles(self):
        styles = styles_for_profile("YouTube")

        for expected in (
            "Dinâmico",
            "Clean",
            "Premium",
            "Highlights",
            "Storytelling",
        ):
            self.assertIn(expected, styles)

    def test_shorts_has_impact_style(self):
        self.assertIn(
            "Impacto",
            styles_for_profile(
                "Shorts / Reels / TikTok"
            ),
        )

    def test_wedding_styles_keep_automatic_silence_cuts_off(self):
        for style in styles_for_profile("Casamento"):
            rules = get_edit_rules("Casamento", style)
            self.assertFalse(
                rules.automatic_silence_cuts
            )

    def test_impact_is_more_aggressive_than_clean(self):
        impact = get_edit_rules(
            "Shorts / Reels / TikTok",
            "Impacto",
        )
        clean = get_edit_rules(
            "Shorts / Reels / TikTok",
            "Clean",
        )

        self.assertLess(
            impact.minimum_silence_ms,
            clean.minimum_silence_ms,
        )
        self.assertLess(
            impact.edge_padding_ms,
            clean.edge_padding_ms,
        )


class StylePresetBehaviorTests(unittest.TestCase):
    def _transcript(self):
        segments = []
        for index in range(8):
            start = index * 6000
            segments.append(
                {
                    "id": index,
                    "start_ms": start,
                    "end_ms": start + 3500,
                    "text": (
                        "Agora vamos mostrar este projeto "
                        "com detalhes importantes para você"
                    ),
                    "words": [],
                }
            )
        return {
            "schema_version": "0.1",
            "segments": segments,
        }

    def test_highlights_generates_more_zoom_than_clean(self):
        transcript = self._transcript()

        highlights = analyze_content(
            transcript,
            profile="YouTube",
            style="Highlights",
        )
        clean = analyze_content(
            transcript,
            profile="YouTube",
            style="Clean",
        )

        self.assertGreater(
            highlights["summary"]["zoom_events"],
            clean["summary"]["zoom_events"],
        )
        self.assertGreater(
            highlights["style_preset"]["zoom_scale"],
            clean["style_preset"]["zoom_scale"],
        )

    def test_cinematic_wedding_disables_zoom_and_broll(self):
        analysis = analyze_content(
            self._transcript(),
            profile="Casamento",
            style="Cinematográfico",
        )

        self.assertEqual(
            analysis["summary"]["zoom_events"],
            0,
        )
        self.assertEqual(
            analysis["summary"]["broll_suggestions"],
            0,
        )


class ProjectStyleDefaultTests(unittest.TestCase):
    def test_project_uses_preset_defaults_when_not_overridden(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.mp4"
            source.write_bytes(b"video")

            manager = ProjectManager(
                root / "projects"
            )
            project = manager.create_project(
                "Impacto",
                source,
                "Shorts / Reels / TikTok",
                "Impacto",
            )
            _, data = manager.load_project(project)

            settings = data["review_settings"]

            self.assertTrue(
                settings["captions_enabled"]
            )
            self.assertTrue(
                settings["auto_zoom"]
            )
            self.assertEqual(
                settings["caption_style"],
                "Impacto",
            )

    def test_render_settings_fall_back_to_style_preset(self):
        settings = default_render_settings(
            {
                "aspect_ratio": "16:9",
                "style": "Premium",
            }
        )

        self.assertTrue(
            settings["auto_zoom"]
        )
        self.assertFalse(
            settings["captions_enabled"]
        )
        self.assertEqual(
            settings["caption_style"],
            "Clean",
        )

    def test_new_styles_build_real_edit_plans(self):
        for profile, style in (
            ("YouTube", "Storytelling"),
            ("YouTube", "Highlights"),
            ("Shorts / Reels / TikTok", "Impacto"),
            ("Casamento", "Emocional"),
        ):
            plan = build_edit_plan(
                10000,
                profile,
                style,
                {"silences": []},
            )
            self.assertEqual(
                plan["style"],
                style,
            )


class FirstPreviewStyleTests(unittest.TestCase):
    def test_dynamic_style_applies_caption_and_content_analysis_on_first_render(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.mp4"
            source.write_bytes(b"source")

            manager = ProjectManager(
                root / "projects"
            )
            project = manager.create_project(
                "Primeira prévia",
                source,
                "YouTube",
                "Dinâmico",
            )

            make_wav(
                project / "audio" / "extracted.wav",
                seconds=1,
            )

            data = transcript()
            data["text"] = (
                "Agora vamos mostrar este projeto "
                "com detalhes importantes para você"
            )
            data["segments"][0]["text"] = data["text"]

            write_json(
                project
                / "transcription"
                / "transcript.json",
                data,
            )
            write_json(
                project
                / "analysis"
                / "silences.json",
                silences(),
            )

            manager.save_media_metadata(
                project,
                {
                    "container": {
                        "duration_seconds": 1.0,
                    },
                    "video": {
                        "width": 1920,
                        "height": 1080,
                    },
                },
            )

            class FakeTools:
                ffmpeg_path = None

            class FakeRenderer:
                def __init__(self):
                    self.calls = []
                    self.last_encoder = SimpleNamespace(
                        label="Teste"
                    )

                def render(
                    self,
                    source,
                    destination,
                    edit_plan,
                    cancel=None,
                    **options,
                ):
                    destination = Path(destination)
                    destination.parent.mkdir(
                        parents=True,
                        exist_ok=True,
                    )
                    destination.write_bytes(
                        b"preview"
                    )
                    self.calls.append(options)
                    return destination

            renderer = FakeRenderer()

            result = AutoEditPipeline(
                manager=manager,
                tools=FakeTools(),
                renderer=renderer,
            ).run(project)

            self.assertEqual(
                len(renderer.calls),
                1,
            )
            options = renderer.calls[0]

            self.assertIsNotNone(
                options["caption_file"]
            )
            self.assertTrue(
                Path(
                    options["caption_file"]
                ).exists()
            )
            self.assertTrue(
                options["zoom_events"]
            )
            self.assertEqual(
                options["target_aspect_ratio"],
                "16:9",
            )
            self.assertTrue(
                (
                    project
                    / "analysis"
                    / "content_analysis.json"
                ).exists()
            )
            self.assertEqual(
                result["review_settings"][
                    "caption_style"
                ],
                "Dinâmica",
            )


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from core.export_pipeline import ExportPipeline
from core.processing import ProcessingError
from core.project_manager import ProjectManager
from core.review_pipeline import ReviewRenderPipeline
from core.storage import write_json
from editor.edit_plan import build_edit_plan
from editor.review import (
    edited_to_source_ms,
    restore_cut,
    source_to_edited_ms,
)
from renderer.export_profiles import get_export_profile
from renderer.ffmpeg_renderer import build_filter_graph


class ReviewPlanTests(unittest.TestCase):
    def setUp(self):
        self.plan = build_edit_plan(
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

    def test_restore_cut_updates_stats(self):
        remove_index = next(
            index
            for index, segment in enumerate(self.plan["segments"])
            if segment["action"] == "remove"
        )

        before = self.plan["stats"]
        restored = restore_cut(self.plan, remove_index)
        after = restored["stats"]

        self.assertEqual(after["cuts"], before["cuts"] - 1)
        self.assertLess(
            after["removed_duration_ms"],
            before["removed_duration_ms"],
        )
        self.assertGreater(
            after["estimated_duration_ms"],
            before["estimated_duration_ms"],
        )

    def test_timeline_mapping_skips_removed_region(self):
        remove = next(
            segment
            for segment in self.plan["segments"]
            if segment["action"] == "remove"
        )

        edited_at_cut = source_to_edited_ms(
            self.plan,
            remove["start_ms"],
        )
        mapped_source = edited_to_source_ms(
            self.plan,
            edited_at_cut,
        )

        self.assertGreaterEqual(
            mapped_source,
            remove["end_ms"],
        )

    def test_export_profiles(self):
        self.assertIsNone(get_export_profile("original").height)
        self.assertEqual(get_export_profile("1080p").height, 1080)
        self.assertEqual(get_export_profile("720p").height, 720)
        self.assertEqual(get_export_profile("480p").height, 480)

    def test_scaled_filter_graph_contains_scale(self):
        graph = build_filter_graph(self.plan, output_height=720)
        self.assertIn("scale=-2:720:flags=lanczos[outv]", graph)


class FakeRenderer:
    def __init__(self):
        self.calls = []

    def render(self, source, destination, edit_plan, cancel=None, **options):
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"fake-video")
        self.calls.append(
            {
                "source": Path(source),
                "destination": destination,
                "plan": edit_plan,
                "options": options,
            }
        )
        return destination


class PipelineTests(unittest.TestCase):
    def _project(
        self,
        root,
        *,
        captions_enabled=False,
        auto_zoom=False,
    ):
        source = root / "source.mp4"
        source.write_bytes(b"source")

        manager = ProjectManager(root / "projects")
        project = manager.create_project(
            "Review",
            source,
            "YouTube",
            "Dinâmico",
            captions_enabled=captions_enabled,
            auto_zoom=auto_zoom,
        )

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
        write_json(project / "decisions" / "edit_plan.json", plan)
        return project, plan

    def test_review_pipeline_writes_new_preview(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, plan = self._project(Path(temporary))
            renderer = FakeRenderer()

            result = ReviewRenderPipeline(
                renderer=renderer
            ).run(project, plan)

            self.assertTrue((project / result["output_path"]).exists())
            self.assertEqual(len(renderer.calls), 1)

            _, project_data = ProjectManager().load_project(project)
            self.assertEqual(
                project_data["output_path"],
                result["output_path"],
            )

    def test_review_requires_transcript_when_captions_are_enabled(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, plan = self._project(
                Path(temporary),
                captions_enabled=True,
            )

            with self.assertRaisesRegex(
                ProcessingError,
                "transcrição",
            ):
                ReviewRenderPipeline(
                    renderer=FakeRenderer()
                ).run(project, plan)

    def test_export_pipeline_uses_selected_profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, _ = self._project(Path(temporary))
            renderer = FakeRenderer()

            result = ExportPipeline(
                renderer=renderer
            ).run(project, "720p")

            self.assertTrue((project / result["export_path"]).exists())
            self.assertEqual(result["export_profile"], "720p")
            self.assertEqual(
                renderer.calls[0]["options"]["output_height"],
                720,
            )
            self.assertEqual(
                renderer.calls[0]["options"]["audio_bitrate"],
                "160k",
            )

    def test_export_requires_transcript_when_captions_are_enabled(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, _ = self._project(
                Path(temporary),
                captions_enabled=True,
            )

            with self.assertRaisesRegex(
                ProcessingError,
                "transcrição",
            ):
                ExportPipeline(
                    renderer=FakeRenderer()
                ).run(project, "720p")

    def test_original_export_reuses_existing_preview(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, _ = self._project(Path(temporary))
            preview = project / "output" / "video_editado.mp4"
            preview.parent.mkdir(parents=True, exist_ok=True)
            preview.write_bytes(b"preview-video")

            manager = ProjectManager()
            manager.update_processing(
                project,
                "rendered",
                output_path="output/video_editado.mp4",
            )

            class FakeTools:
                def probe(self, path, cancel=None):
                    return {"video": {"height": 1080}}

            renderer = FakeRenderer()
            result = ExportPipeline(
                tools=FakeTools(),
                renderer=renderer,
            ).run(project, "original")

            self.assertTrue((project / result["export_path"]).exists())
            self.assertEqual(
                (project / result["export_path"]).read_bytes(),
                b"preview-video",
            )
            self.assertEqual(result["export_mode"], "smart_copy")
            self.assertEqual(renderer.calls, [])


if __name__ == "__main__":
    unittest.main()
